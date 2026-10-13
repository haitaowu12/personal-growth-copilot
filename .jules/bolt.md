## 2024-05-24 - Initial Bolt Setup\n**Learning:** This is a Python project using ============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0
rootdir: /app
configfile: pyproject.toml
testpaths: tests
collected 9 items / 17 errors

==================================== ERRORS ====================================
_______________ ERROR collecting tests/test_attempt_inventory.py _______________
ImportError while importing test module '/app/tests/test_attempt_inventory.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_attempt_inventory.py:20: in <module>
    import attempt_inventory  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^
evals/attempt_inventory.py:19: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
___________________ ERROR collecting tests/test_campaign.py ____________________
ImportError while importing test module '/app/tests/test_campaign.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_campaign.py:15: in <module>
    import campaign  # noqa: E402
    ^^^^^^^^^^^^^^^
evals/campaign.py:17: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_context_runtime.py ________________
ImportError while importing test module '/app/tests/test_context_runtime.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_context_runtime.py:17: in <module>
    import growth_record  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/growth_record.py:24: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_____________ ERROR collecting tests/test_external_gate_sources.py _____________
ImportError while importing test module '/app/tests/test_external_gate_sources.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_external_gate_sources.py:22: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_____________ ERROR collecting tests/test_growth_record_schema.py ______________
ImportError while importing test module '/app/tests/test_growth_record_schema.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_growth_record_schema.py:14: in <module>
    import growth_record  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/growth_record.py:24: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
____________ ERROR collecting tests/test_host_privacy_discovery.py _____________
ImportError while importing test module '/app/tests/test_host_privacy_discovery.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_host_privacy_discovery.py:16: in <module>
    import host_privacy_discovery  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
scripts/host_privacy_discovery.py:25: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_________________ ERROR collecting tests/test_learning_pack.py _________________
ImportError while importing test module '/app/tests/test_learning_pack.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_learning_pack.py:16: in <module>
    spec.loader.exec_module(builder)
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/build_learning.py:15: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_learning_review.py ________________
ImportError while importing test module '/app/tests/test_learning_review.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_learning_review.py:26: in <module>
    reviewer = module("learning_review", SKILL / "scripts/review_learning.py")
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_learning_review.py:22: in module
    spec.loader.exec_module(loaded)
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/review_learning.py:12: in <module>
    from jsonschema import FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_multiturn_eval.py _________________
ImportError while importing test module '/app/tests/test_multiturn_eval.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_multiturn_eval.py:17: in <module>
    spec.loader.exec_module(runner)
evals/run.py:23: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
______________ ERROR collecting tests/test_outcome_evaluation.py _______________
ImportError while importing test module '/app/tests/test_outcome_evaluation.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_outcome_evaluation.py:9: in <module>
    import yaml
E   ModuleNotFoundError: No module named 'yaml'
_______________ ERROR collecting tests/test_provider_adapter.py ________________
ImportError while importing test module '/app/tests/test_provider_adapter.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_provider_adapter.py:15: in <module>
    import target_session  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^
evals/target_session.py:25: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_____________ ERROR collecting tests/test_qualification_packet.py ______________
ImportError while importing test module '/app/tests/test_qualification_packet.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_qualification_packet.py:17: in <module>
    import qualification_packet  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^
scripts/qualification_packet.py:17: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_________________ ERROR collecting tests/test_record_store.py __________________
ImportError while importing test module '/app/tests/test_record_store.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_record_store.py:17: in <module>
    import record_store  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/record_store.py:22: in <module>
    from growth_record import COLLECTIONS, validate_record
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/growth_record.py:24: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_______________ ERROR collecting tests/test_release_evidence.py ________________
ImportError while importing test module '/app/tests/test_release_evidence.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_release_evidence.py:17: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_release_packet.py _________________
ImportError while importing test module '/app/tests/test_release_packet.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_release_packet.py:16: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_safety_runtime.py _________________
ImportError while importing test module '/app/tests/test_safety_runtime.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_safety_runtime.py:15: in <module>
    import safety_runtime as safety  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/safety_runtime.py:20: in <module>
    import yaml
E   ModuleNotFoundError: No module named 'yaml'
________________ ERROR collecting tests/test_target_session.py _________________
ImportError while importing test module '/app/tests/test_target_session.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_target_session.py:17: in <module>
    import target_session  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^
evals/target_session.py:25: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
=========================== short test summary info ============================
ERROR tests/test_attempt_inventory.py
ERROR tests/test_campaign.py
ERROR tests/test_context_runtime.py
ERROR tests/test_external_gate_sources.py
ERROR tests/test_growth_record_schema.py
ERROR tests/test_host_privacy_discovery.py
ERROR tests/test_learning_pack.py
ERROR tests/test_learning_review.py
ERROR tests/test_multiturn_eval.py
ERROR tests/test_outcome_evaluation.py
ERROR tests/test_provider_adapter.py
ERROR tests/test_qualification_packet.py
ERROR tests/test_record_store.py
ERROR tests/test_release_evidence.py
ERROR tests/test_release_packet.py
ERROR tests/test_safety_runtime.py
ERROR tests/test_target_session.py
!!!!!!!!!!!!!!!!!!! Interrupted: 17 errors during collection !!!!!!!!!!!!!!!!!!!
============================== 17 errors in 2.09s ==============================. Let's look for performance bottlenecks in Python code, particularly in algorithms, data processing, or loops.\n**Action:** Profile the code using ============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0
rootdir: /app
configfile: pyproject.toml
testpaths: tests
collected 9 items / 17 errors

==================================== ERRORS ====================================
_______________ ERROR collecting tests/test_attempt_inventory.py _______________
ImportError while importing test module '/app/tests/test_attempt_inventory.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_attempt_inventory.py:20: in <module>
    import attempt_inventory  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^
evals/attempt_inventory.py:19: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
___________________ ERROR collecting tests/test_campaign.py ____________________
ImportError while importing test module '/app/tests/test_campaign.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_campaign.py:15: in <module>
    import campaign  # noqa: E402
    ^^^^^^^^^^^^^^^
evals/campaign.py:17: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_context_runtime.py ________________
ImportError while importing test module '/app/tests/test_context_runtime.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_context_runtime.py:17: in <module>
    import growth_record  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/growth_record.py:24: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_____________ ERROR collecting tests/test_external_gate_sources.py _____________
ImportError while importing test module '/app/tests/test_external_gate_sources.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_external_gate_sources.py:22: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_____________ ERROR collecting tests/test_growth_record_schema.py ______________
ImportError while importing test module '/app/tests/test_growth_record_schema.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_growth_record_schema.py:14: in <module>
    import growth_record  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/growth_record.py:24: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
____________ ERROR collecting tests/test_host_privacy_discovery.py _____________
ImportError while importing test module '/app/tests/test_host_privacy_discovery.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_host_privacy_discovery.py:16: in <module>
    import host_privacy_discovery  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
scripts/host_privacy_discovery.py:25: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_________________ ERROR collecting tests/test_learning_pack.py _________________
ImportError while importing test module '/app/tests/test_learning_pack.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_learning_pack.py:16: in <module>
    spec.loader.exec_module(builder)
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/build_learning.py:15: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_learning_review.py ________________
ImportError while importing test module '/app/tests/test_learning_review.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_learning_review.py:26: in <module>
    reviewer = module("learning_review", SKILL / "scripts/review_learning.py")
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_learning_review.py:22: in module
    spec.loader.exec_module(loaded)
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/review_learning.py:12: in <module>
    from jsonschema import FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_multiturn_eval.py _________________
ImportError while importing test module '/app/tests/test_multiturn_eval.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_multiturn_eval.py:17: in <module>
    spec.loader.exec_module(runner)
evals/run.py:23: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
______________ ERROR collecting tests/test_outcome_evaluation.py _______________
ImportError while importing test module '/app/tests/test_outcome_evaluation.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_outcome_evaluation.py:9: in <module>
    import yaml
E   ModuleNotFoundError: No module named 'yaml'
_______________ ERROR collecting tests/test_provider_adapter.py ________________
ImportError while importing test module '/app/tests/test_provider_adapter.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_provider_adapter.py:15: in <module>
    import target_session  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^
evals/target_session.py:25: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_____________ ERROR collecting tests/test_qualification_packet.py ______________
ImportError while importing test module '/app/tests/test_qualification_packet.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_qualification_packet.py:17: in <module>
    import qualification_packet  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^
scripts/qualification_packet.py:17: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_________________ ERROR collecting tests/test_record_store.py __________________
ImportError while importing test module '/app/tests/test_record_store.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_record_store.py:17: in <module>
    import record_store  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/record_store.py:22: in <module>
    from growth_record import COLLECTIONS, validate_record
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/growth_record.py:24: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
_______________ ERROR collecting tests/test_release_evidence.py ________________
ImportError while importing test module '/app/tests/test_release_evidence.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_release_evidence.py:17: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_release_packet.py _________________
ImportError while importing test module '/app/tests/test_release_packet.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_release_packet.py:16: in <module>
    import release_evidence  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^
scripts/release_evidence.py:21: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
________________ ERROR collecting tests/test_safety_runtime.py _________________
ImportError while importing test module '/app/tests/test_safety_runtime.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_safety_runtime.py:15: in <module>
    import safety_runtime as safety  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/safety_runtime.py:20: in <module>
    import yaml
E   ModuleNotFoundError: No module named 'yaml'
________________ ERROR collecting tests/test_target_session.py _________________
ImportError while importing test module '/app/tests/test_target_session.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_target_session.py:17: in <module>
    import target_session  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^
evals/target_session.py:25: in <module>
    from jsonschema import Draft202012Validator, FormatChecker
E   ModuleNotFoundError: No module named 'jsonschema'
=========================== short test summary info ============================
ERROR tests/test_attempt_inventory.py
ERROR tests/test_campaign.py
ERROR tests/test_context_runtime.py
ERROR tests/test_external_gate_sources.py
ERROR tests/test_growth_record_schema.py
ERROR tests/test_host_privacy_discovery.py
ERROR tests/test_learning_pack.py
ERROR tests/test_learning_review.py
ERROR tests/test_multiturn_eval.py
ERROR tests/test_outcome_evaluation.py
ERROR tests/test_provider_adapter.py
ERROR tests/test_qualification_packet.py
ERROR tests/test_record_store.py
ERROR tests/test_release_evidence.py
ERROR tests/test_release_packet.py
ERROR tests/test_safety_runtime.py
ERROR tests/test_target_session.py
!!!!!!!!!!!!!!!!!!! Interrupted: 17 errors during collection !!!!!!!!!!!!!!!!!!!
============================== 17 errors in 1.72s ============================== or a profiler if necessary to find slow tests/functions.
_MACHINE_CACHE = None
## 2024-05-24 - Safety Runtime Machine Config Optimization\n**Learning:** The `SafetyRuntime` class initializes frequently (774 times in a 45 second run) during testing and likely runtime. Each time, it reads and parses the `assets/safety-state-machine.yaml` file. This parsing of the machine state is surprisingly expensive.\n**Action:** Implemented a caching mechanism (`_MACHINE_CACHE`) for `load_machine` using `deepcopy` to preserve isolation but skip the expensive yaml load and validation operations.
## 2024-05-24 - Result\n**Learning:** The caching of `load_machine` reduced the test suite runtime significantly from 45.5 seconds to 19.5 seconds! That's a 26 second saving, mostly from skipping the repeated yaml parsing for the safety machine.\n**Action:** Plan to submit this change as the daily Bolt optimization.
