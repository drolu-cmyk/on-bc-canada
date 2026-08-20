# Control-plane reference slice

`control_plane.py` is a small, provider-neutral reference implementation of
the enrollment-to-onboarding standard path. It is deliberately local and uses
no credentials, cloud services, or learner personal information. The future AWS
implementation should preserve the event names, idempotency behavior, privacy
boundary, and human-review routes defined here.

Run the tests from this directory:

```bash
python -m unittest -v
```

The local ledger is not a production database. It exists to make the contract
replayable before adding AWS EventBridge, SQS, DynamoDB, S3, or collaboration
adapters.
