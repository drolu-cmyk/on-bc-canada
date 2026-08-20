# Public launch

Applied AI Training for Canada publishes a static information shell before learner services are enabled. The shell describes the program, curriculum, accessibility route, support route, privacy boundary, terms, and enrollment status.

## Public artifact

The `site/` directory is the canonical static artifact. It contains no live intake, account creation, learner workspace, analytics form, advertising tracker, or external model call. The build workflow validates the pages and publishes a reviewable artifact for the deployment owner.

## Canonical domain

The canonical public origin is `https://www.sozorock.ca`. The CloudFront distribution serves this hostname through an AWS Certificate Manager certificate in `us-east-1`. DNS routes `www.sozorock.ca` to the CloudFront distribution domain name emitted by the stack. The hosting reference region is AWS Canada Central (`ca-central-1`).

## AWS hosting contract

`infra/public-site.template.json` defines a private S3 origin and a CloudFront distribution. The template enforces S3 public-access blocking, bucket encryption, object ownership, versioning, HTTPS redirection, and GET/HEAD-only delivery. The deployment reference region is AWS Canada Central (`ca-central-1`).

The template does not create learner databases, intake endpoints, model endpoints, credentials, or communication services. Learner services remain disabled in `config/deployment.yaml`.

## Release gates

The public release path runs specification, public-copy, site, deployment, compiler, runtime, and release-manifest checks. A deployment owner authorizes infrastructure publication after the source, artifact, region, access, privacy, and rollback records are present.

The source-only status remains active until a configured environment supplies an approved bucket name, AWS account, deployment role, ACM certificate in `us-east-1`, DNS routing, monitoring route, and human authorization. No learner data enters the public artifact.

## Artifact flow

```text
versioned source
  -> validation
  -> static artifact
  -> deployment owner authorization
  -> private S3 origin
  -> CloudFront HTTPS delivery
```

The public information shell is separate from learner operations. Adding an enrollment endpoint requires a separate release record, data-flow approval, privacy decision, accessibility check, security review, and human authorization.
