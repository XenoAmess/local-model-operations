# Review a bounded dispatch DATA plan

[The planner](../scripts/authorized_dispatch/authorized_dispatch_plan.py) turns an explicit roster snapshot and authorized pending bundle into a reviewable JSON plan. It never calls collaboration tools, starts agents, follows evidence links, selects models or contacts a network. Its `actual_start` field stays `false`; the coordinator must separately verify authority and dispatch any accepted item.

The [complete schema and decision order](../scripts/authorized_dispatch/PUBLIC-API.v3.txt) are versioned inputs. A RUNNING owner may receive `SEND`; a COMPLETED owner needs `FOLLOWUP` to start a turn. Only an explicitly classified CAPACITY error with exactly matching task identity and a matching live grant may produce `SAME_TASK_RETRY`, using `followup_task`. GUARD refuses retry, INTERRUPTED and revoked grants remain stopped, and unknown or missing status does not become completion. Root cannot be a followup target. No output changes the execution machine's currently selected model.

Input status, grants and error classifications are supplied assertions. The program validates their shape, freshness and identity; it cannot establish that they are true or authorized. A matching SHA checks the exact UTF-8 task body. Ordered write roots must match exactly. Path checking is lexical and does not establish filesystem containment or operating-system permissions.

The bounded contract accepts two strict UTF-8 JSON byte objects, each at most 1 MiB; at most 65 agents, grants or tasks; explicit UTC and maximum age; and a plan capped at 2 MiB. Duplicate keys, unsupported fields, JSON floats/nonfinite values, invalid identities and inconsistent counts reject. The CLI accepts canonical Windows D-drive input and output paths only. It validates the full plan before exclusively creating the output; it does not overwrite an existing file.

Use the execution machine's configured Python executable as the first command token. Replace every placeholder with an actual reviewed local input or new output path:

```text
python -B scripts/authorized_dispatch/authorized_dispatch_plan.py --snapshot ABSOLUTE_D_SNAPSHOT --pending ABSOLUTE_D_PENDING --now EXPLICIT_UTC --max-age-seconds 60 --max-plans 65 --output ABSOLUTE_D_NEW_PLAN
```

The [synthetic snapshot](../scripts/authorized_dispatch/fixtures/SYNTHETIC-SNAPSHOT.json) and [pending fixture](../scripts/authorized_dispatch/fixtures/SYNTHETIC-PENDING.json) are sample DATA, not an observed roster or permission to act. They contain 65 fictional entries and one explicit task. For a new necessary CLI verification, copy the two fixture files as DATA into an owned D-drive directory and use `2026-01-01T00:00:17Z` as the explicit fixture clock. Producing one SEND item is still only DATA.

The [manual witness](../scripts/authorized_dispatch/test_authorized_dispatch_plan.py) requires `DISPATCH_PLANNER_TEST_DATA_ROOT` to name an existing owned D-drive scratch parent. Its CLI method creates and cleans a temporary child. Invoke the witness explicitly with Python; importing or executing these examples is a separate action from reading the package.

The [qualification record](evidence/2026-11-04-http-authorized-dispatch-planner03.json) distinguishes the original private source baseline from this public fixture projection. The two production modules preserve the original bytes that passed ten finite DATA methods and one historical CLI check. Eight test method bodies and the three fixture-support functions remain unchanged. Two method entry points now use explicit scratch storage and relative synthetic fixtures; those changed bindings and a new synthetic CLI check have not run at this publication cutoff. The original ten methods are not reported as a new portable-suite pass.

The model supplied part of the decision function. Two corrections came from the owner's incomplete external tool contract: capacity recovery must start the existing owner with followup, and followup supports only a non-root target. The original requests remain unchanged. Model HTTP time, source preparation, software child time and subsequent real coordinator use are recorded separately. No net preparation saving, automatic dispatch, current global coverage or performance gain has been established.
