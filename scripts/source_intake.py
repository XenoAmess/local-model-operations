"""Explicit trusted-registrar loop and rejection-observation component.

The operator supplies all three absolute paths. The registrar is executable
trusted Python, loaded and invoked by this program; it is not ticket DATA or
a sandboxed plugin. Review and qualify the entire registrar contract first.
Only the operator may reconcile stopped writers and preserve legacy claims.
Persistent OS lock sidecars are never removed or stolen by PID or age.
"""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

MAX_SCAN_FILES = 4096


def _registrar(path):
    spec = importlib.util.spec_from_file_location('owned_intake_registrar', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAX_REJECTIONS = 4096
SAFE_TICKET_NAME = re.compile(r'[A-Za-z0-9_-]{1,180}\.ready\.json')


def _owned_directory(root, name):
    path = root / name
    path.mkdir(exist_ok=True)
    if (not path.is_dir() or path.is_symlink()
            or getattr(path, 'is_junction', lambda: False)()
            or path.resolve(strict=True) != root / name):
        raise ValueError('INTAKE_OBSERVATION_DIRECTORY_REQUIRES_RECONCILIATION')
    return path


def _candidate_issue(intake, path):
    if (path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
            or not path.is_file()):
        return 'INTAKE_NONREGULAR_ENTRY'
    if path.resolve(strict=True).parent != intake:
        return 'INTAKE_PATH_OUTSIDE'
    return None


def _metadata_reason(reg, failure):
    if isinstance(failure, reg.RegistrationError):
        reason = str(failure)
        if re.fullmatch(r'[A-Z][A-Z0-9_]{0,95}', reason):
            return reason
    if isinstance(failure, UnicodeError):
        return 'METADATA_ENCODING_INVALID'
    if isinstance(failure, RecursionError):
        return 'METADATA_NESTING_LIMIT'
    if isinstance(failure, OSError):
        return 'METADATA_READ_UNAVAILABLE'
    return 'METADATA_INVALID_JSON_OR_SCHEMA'


def _observe_rejection(root, reg, path, raw, failure, reason):
    directory = _owned_directory(root, 'INTAKE-REJECTIONS')
    name_bytes = path.name.encode('utf-8', errors='surrogatepass')
    raw_sha = None if raw is None else reg.sha(raw)
    marker = (b'unavailable:' + reason.encode('ascii') if raw_sha is None
              else b'raw:' + raw_sha.encode('ascii'))
    token = reg.sha(b'intake-rejection-observation/v1\0' + name_bytes + b'\0' + marker)
    destination = directory / (token + '.rejection.json')
    value = {'schema': 'source-intake-rejection-observation/v1',
             'stage': 'INTAKE_REJECTED_BEFORE_REGISTRATION_OBSERVATION',
             'input_name_escaped': path.name.encode('unicode_escape').decode('ascii'),
             'filename_sha256': reg.sha(name_bytes),
             'input_bytes': None if raw is None else len(raw),
             'input_sha256': raw_sha,
             'error': type(failure).__name__[:96], 'reason': reason,
             'registration_attempted': False, 'final_receipt': False, 'POST_credit': False}
    encoded = reg.js(value)
    if (destination.is_symlink() or getattr(destination, 'is_junction', lambda: False)()
            or (destination.exists() and not destination.is_file())):
        raise ValueError('REJECTION_OBSERVATION_PATH_REQUIRES_RECONCILIATION')
    if destination.exists():
        if reg.bounded_read(destination, reg.MAX_METADATA) != encoded:
            raise ValueError('REJECTION_OBSERVATION_IMMUTABLE_CONFLICT')
        return None
    count = 0
    for _ in directory.iterdir():
        count += 1
        if count >= MAX_REJECTIONS:
            raise ValueError('REJECTION_OBSERVATION_BOUND_REQUIRES_OWNER_ARCHIVE')
    try:
        reg.atomic_file(destination, encoded, create_only=True)
    except FileExistsError:
        if (destination.is_symlink() or not destination.is_file()
                or reg.bounded_read(destination, reg.MAX_METADATA) != encoded):
            raise ValueError('REJECTION_OBSERVATION_IMMUTABLE_CONFLICT') from None
        return None
    return value


def _save_scan(root, reg, counts, *, complete, classified, pending):
    value = {'schema': 'source-intake-bounded-scan/v1',
             'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'scope': 'EXPLICIT_BOUNDED_INTAKE_ENUMERATION_NOT_ATOMIC_ACROSS_FILES',
             **counts, 'processing_complete': complete,
             'unclassified_pending': pending - classified,
             'counter_semantics': 'receipt/pending counts are at enumeration; classification and registration counts are this pass',
             'actual_registered_tasks': None, 'HTTP_inflight': None,
             'global_state': 'UNKNOWN', 'POST_credit': False}
    reg.atomic_file(root / 'INTAKE-SCAN.STATE.json', reg.js(value))


def _once(root, reg, repo, max_pending):
    if type(max_pending) is not int or not 1 <= max_pending <= 256:
        raise ValueError('PENDING_BATCH_BOUND')
    intake = _owned_directory(root, 'INTAKE')
    receipts = _owned_directory(root, 'INTAKE-RECEIPTS')
    names = []
    for path in intake.glob('*.ready.json'):
        if len(names) >= MAX_SCAN_FILES:
            raise ValueError('INTAKE_DIRECTORY_BOUND_REQUIRES_OWNER_ARCHIVE')
        names.append(path)
    pending = []
    for path in sorted(names):
        if (SAFE_TICKET_NAME.fullmatch(path.name)
                and (receipts / (path.name + '.receipt.json')).exists()):
            continue
        pending.append(path)
    counts = {'seen_ready_tickets': len(names),
              'tickets_with_final_receipt': len(names) - len(pending),
              'tickets_without_final_receipt': len(pending),
              'rejected_before_registration': 0, 'valid_metadata_pending': 0,
              'registration_attempts': 0, 'accepted_registration_results': 0,
              'reconciliation_results': 0, 'capacity_deferred': 0}
    results, classified, processed = [], 0, 0
    complete = True
    for path in pending:
        if (root / 'INTAKE-STOP.json').exists():
            complete = False
            break
        raw = None
        try:
            if not SAFE_TICKET_NAME.fullmatch(path.name):
                raise reg.RegistrationError('INVALID_INTAKE_FILENAME')
            issue = _candidate_issue(intake, path)
            if issue is not None:
                raise reg.RegistrationError(issue)
            raw = reg.bounded_read(path, reg.MAX_METADATA)
            incoming = reg._metadata(raw)
        except (OSError, ValueError, UnicodeError, RecursionError) as failure:
            reason = _metadata_reason(reg, failure)
            observed = _observe_rejection(root, reg, path, raw, failure, reason)
            counts['rejected_before_registration'] += 1
            classified += 1
            if observed is not None:
                results.append(observed)
            continue
        counts['valid_metadata_pending'] += 1
        classified += 1
        if processed >= max_pending:
            complete = False
            break
        processed += 1
        receipt = receipts / (path.name + '.receipt.json')
        try:
            if 'spec_sha256' not in incoming:
                incoming['spec_sha256'] = reg.sha(reg.bounded_read(incoming['spec_path'], reg.MAX_SPEC))
            if reg.bounded_read(path, reg.MAX_METADATA) != raw:
                raise ValueError('INTAKE_CHANGED_DURING_READ')
            normalized = receipts / (path.name + '.normalized.json')
            reg.immutable_file(normalized, reg.js(incoming))
            command = [sys.executable, '-B', '-X', 'utf8', str(Path(reg.__file__).resolve()),
                       str(normalized), '--root', str(root), '--repo', str(repo)]
            counts['registration_attempts'] += 1
            completed = subprocess.run(command, capture_output=True, text=True,
                                       encoding='utf-8', timeout=120, shell=False,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if completed.returncode == 3:
                if len(completed.stdout.encode('utf-8')) > reg.MAX_METADATA:
                    raise ValueError('REGISTRAR_RESULT_BOUND_REQUIRES_RECONCILIATION')
                deferred = reg.strict_json(completed.stdout.encode('utf-8'), bom=False)
                if (type(deferred) is not dict or set(deferred) != {'stage', 'this_attempt_appended_READY', 'reason'}
                        or deferred['stage'] != 'QUEUE_CAPACITY_DEFERRED_BEFORE_READY_APPEND'
                        or deferred['this_attempt_appended_READY'] is not False
                        or deferred['reason'] not in ('QUEUE_BYTE_LIMIT', 'QUEUE_RECORD_LIMIT')):
                    raise ValueError('CAPACITY_RESULT_REQUIRES_RECONCILIATION')
                results.append({'input_path': str(path), 'input_sha256': reg.sha(raw),
                                'id': incoming['id'], 'task_id': incoming['task_id'], **deferred})
                counts['capacity_deferred'] += 1
                complete = False
                break
            if completed.returncode != 0:
                raise ValueError('REGISTRAR_EXIT_REQUIRES_RECONCILIATION:' + str(completed.returncode))
            if len(completed.stdout.encode('utf-8')) > reg.MAX_METADATA:
                raise ValueError('REGISTRAR_RESULT_BOUND_REQUIRES_RECONCILIATION')
            result = reg.strict_json(completed.stdout.encode('utf-8'), bom=False)
            if not isinstance(result, dict) or result.get('stage') not in {
                    'READY_ATOMICALLY_APPENDED_NOT_POST_CREDIT',
                    'ALREADY_REGISTERED_NOT_REPLAYED'}:
                raise ValueError('REGISTRAR_RESULT_REQUIRES_RECONCILIATION')
        except Exception as failure:
            result = {'stage': 'INTAKE_RECONCILIATION_REQUIRED_NO_AUTO_RETRY',
                      'error': type(failure).__name__, 'reason': str(failure)[:4096]}
        value = {'input_path': str(path), 'input_sha256': reg.sha(raw),
                 'id': incoming['id'], 'task_id': incoming['task_id'], **result}
        reg.immutable_file(receipt, reg.js(value))
        if result['stage'] == 'INTAKE_RECONCILIATION_REQUIRED_NO_AUTO_RETRY':
            counts['reconciliation_results'] += 1
        else:
            counts['accepted_registration_results'] += 1
        results.append(value)
    _save_scan(root, reg, counts, complete=complete, classified=classified, pending=len(pending))
    return results


def process_once(*, root, registrar_path, repo, max_pending=256):
    if not Path(root).is_absolute() or not Path(registrar_path).is_absolute() or not Path(repo).is_absolute():
        raise ValueError('ABSOLUTE_INPUT_PATHS_REQUIRED')
    root = Path(root).resolve(strict=True)
    reg = _registrar(registrar_path)
    if any(root.glob('INTAKE-LOOP*.claim*')):
        raise ValueError('LEGACY_CLAIM_REQUIRES_CONFIRMED_OWNER_HANDOFF')
    with reg.exclusive_file_lock(root / 'INTAKE-LOOP.lock', 0):
        return _once(root, reg, Path(repo), max_pending)


def run(*, root, registrar_path, repo, poll_seconds=0.5):
    if type(poll_seconds) not in (int, float) or not 0.05 <= poll_seconds <= 60:
        raise ValueError('POLL_BOUND')
    if not Path(root).is_absolute() or not Path(registrar_path).is_absolute() or not Path(repo).is_absolute():
        raise ValueError('ABSOLUTE_INPUT_PATHS_REQUIRED')
    root = Path(root).resolve(strict=True)
    reg = _registrar(registrar_path)
    if any(root.glob('INTAKE-LOOP*.claim*')):
        raise ValueError('LEGACY_CLAIM_REQUIRES_CONFIRMED_OWNER_HANDOFF')
    with reg.exclusive_file_lock(root / 'INTAKE-LOOP.lock', 0):
        reg.atomic_file(root / 'INTAKE-LOOP.STATE.json', reg.js({'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'state': 'LOCK_HELD_NOT_POST_CREDIT'}))
        while not (root / 'INTAKE-STOP.json').exists():
            following = _once(root, reg, Path(repo), 256)
            for result in following:
                print(json.dumps(result, ensure_ascii=False), flush=True)
            deferred = any(item.get('stage') == 'QUEUE_CAPACITY_DEFERRED_BEFORE_READY_APPEND' for item in following)
            time.sleep(max(poll_seconds, 2.0) if deferred else poll_seconds)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--registrar', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.once:
            print(json.dumps(process_once(root=args.root, registrar_path=args.registrar, repo=args.repo), ensure_ascii=False))
        else:
            run(root=args.root, registrar_path=args.registrar, repo=args.repo)
    except (OSError, ValueError) as failure:
        print(json.dumps({'stage': 'INTAKE_STOPPED_RECONCILIATION_REQUIRED', 'error': type(failure).__name__, 'reason': str(failure)[:4096]}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
