# Pull Request / AI Review Checklist

- [ ] Change matches scope; no unrelated changes or unnecessary dependencies.
- [ ] All inputs validated; correct authorization and least-privilege access.
- [ ] No secrets/PII in code, logs, prompts, fixtures or Git history.
- [ ] No arbitrary model-generated SQL or uncontrolled write-capable tools.
- [ ] Prompt injection and unsupported answer cases handled; source citations checkable.
- [ ] API failure modes: timeouts, retries, duplicates, concurrency, transaction handling.
- [ ] Migration has safe upgrade path, indexes and appropriate constraints.
- [ ] Added tests fail before fix and pass after; no mocked-only happy path.
- [ ] Python typecheck/lint/tests and frontend typecheck/lint/tests/build run.
- [ ] Accessibility, loading/empty/error states, mobile UI verified.
- [ ] Diff reviewed for critical, high and medium findings; unresolved risks documented.
- [ ] README and .env.example updated; no unapproved paid services.
