"""Pure configuration for a separate, empty non-Git read-only audit cwd.

This does not launch OpenCode, perform maintenance, capture HTTP, copy a DB,
or prove filesystem/symlink isolation. The caller supplies a trusted source
tree and checks the installed client's actual permission coordinates. The
Windows OpenCode 1.19.5 runbook is docs/opencode-readonly.md.
"""
from __future__ import annotations

import argparse
import json
import sys

from opencode_config import (
    ConfigError, MODEL_LIMIT_CONTEXT, _split_flavored,
    _validate_executor, _validate_max_output_tokens,
)


def build_readonly_config(executor, *, source_root, max_output_tokens=16000):
    """Generate zero edit grants; launch from an empty non-Git directory.

    The actual non-Git worktree sentinel is '/'. On tested Windows 1.19.5,
    read asks drive-root-relative patterns; glob/grep ask query patterns,
    with their directory boundary checked by external_directory.
    """
    base_url, model = _validate_executor(executor)
    limit = _validate_max_output_tokens(max_output_tokens)
    flavor, anchor, parts = _split_flavored(source_root)
    if not parts:
        raise ConfigError('source_root must be narrower than a filesystem root')
    tail = '/'.join(parts)
    absolute = anchor + tail
    external = {absolute + '/**': 'allow'}
    if flavor == 'windows':
        external[anchor[0].upper() + absolute[1:] + '/**'] = 'allow'
    permission = {
        '*': 'deny',
        'read': {'*': 'deny', tail + '/**': 'allow'},
        'glob': 'allow', 'grep': 'allow', 'invalid': 'allow',
        'external_directory': {'*': 'deny', **external},
    }
    return {
        '$schema': 'https://opencode.ai/config.json',
        'model': 'pilot/' + model, 'small_model': 'pilot/' + model,
        'default_agent': 'pilot', 'enabled_providers': ['pilot'],
        'provider': {'pilot': {
            'npm': '@ai-sdk/openai-compatible',
            'name': 'Shared executor read-only audit',
            'options': {'baseURL': base_url, 'apiKey': 'local'},
            'models': {model: {
                'name': model, 'tool_call': True, 'temperature': True,
                'limit': {'context': MODEL_LIMIT_CONTEXT, 'output': limit},
                'options': {
                    'stream_options': {'include_usage': True},
                    'chat_template_kwargs': {'enable_thinking': False},
                },
            }},
        }},
        'agent': {'pilot': {
            'mode': 'primary', 'description': 'Read-only source audit',
            'temperature': 0, 'permission': {
                k: dict(v) if isinstance(v, dict) else v for k, v in permission.items()
            },
            'prompt': ('Read/glob/grep only the authorized source tree ' + absolute
                       + '. Launch cwd is deliberately empty and outside that tree. '
                       'No editing, commands, delegation, network or business actions. '
                       'Use actual tool schemas and bounded read offsets/limits. '
                       'Report source evidence and uncertainty; do not claim tests ran.'),
        }},
        'permission': permission,
        'share': 'disabled', 'snapshot': False, 'autoupdate': False,
        'plugin': [], 'mcp': {}, 'formatter': False, 'lsp': False,
        'compaction': {'auto': False, 'prune': False}, 'instructions': [],
    }


def isolated_environment(*, config, config_dir, data_dir, state_dir, cache_dir):
    """Return overrides for the caller's child environment; no I/O or launch.

    Parent project config otherwise loads after OPENCODE_CONFIG in 1.19.5.
    Preserve the original recorded config rather than moving/editing it.
    """
    return {
        'OPENCODE_CONFIG': str(config), 'OPENCODE_CONFIG_DIR': str(config_dir),
        'OPENCODE_CONFIG_CONTENT': '', 'OPENCODE_PERMISSION': '',
        'OPENCODE_DISABLE_PROJECT_CONFIG': 'true',
        'OPENCODE_DISABLE_AUTOUPDATE': 'true',
        'OPENCODE_DISABLE_MODELS_FETCH': 'true', 'OPENCODE_DISABLE_SHARE': 'true',
        'XDG_CONFIG_HOME': str(config_dir), 'XDG_DATA_HOME': str(data_dir),
        'XDG_STATE_HOME': str(state_dir), 'XDG_CACHE_HOME': str(cache_dir),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--executor', required=True)
    ap.add_argument('--source-root', required=True)
    ap.add_argument('--max-output-tokens', type=int, default=16000)
    args = ap.parse_args(argv)
    try:
        with open(args.executor, encoding='utf-8') as f:
            executor = json.load(f)
        result = build_readonly_config(executor, source_root=args.source_root,
                                      max_output_tokens=args.max_output_tokens)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
