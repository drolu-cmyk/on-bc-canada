# Curriculum compiler

This compiler turns reviewed YAML module specifications into a deterministic,
portable release package. It does not call a model, cloud service, or external
provider. Authoring assistance may use a provider, but the committed source
specification and human release gates remain the source of truth.

Run locally from the repository root:

```bash
PYTHONPATH=compiler/src python -m curriculum_compiler.compile \
  --source content/modules \
  --output generated \
  --program-id applied-ai-training-canada \
  --release-version 0.1.0
```

The output contains learner pages, instructor run-of-show JSON, safe-lab briefs,
rubrics, feedback forms, an evidence index, checks, and a release manifest with
source and artifact hashes. The generated package is disposable; reviewed source
specifications are versioned in Git.

Run the offline tests:

```bash
PYTHONPATH=compiler/src python -m unittest discover -s compiler/tests -v
```
