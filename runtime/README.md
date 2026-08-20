# Control-plane reference slice

`control_plane.py` is a small, provider-neutral reference implementation of the enrollment-to-onboarding standard path. It is local and uses no credentials, cloud services, or learner personal information. AWS implementations preserve the event names, idempotency behavior, privacy boundary, and human-review routes defined here.

The local ledger is not a production database. It makes the contract replayable before AWS EventBridge, SQS, DynamoDB, S3, or collaboration adapters receive learner data or produce external side effects.

Run the tests from this directory:

```bash
python -m unittest -v
```
