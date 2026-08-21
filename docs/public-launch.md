# Public launch

Applied AI Training for Canada publishes a static information shell before learner services are enabled. The shell describes the program, curriculum, accessibility route, support route, privacy boundary, terms, and enrollment status.

## Public artifact

The `site/` directory is the canonical static artifact. It contains no live intake, account creation, learner workspace, analytics form, advertising tracker, or external model call. The build workflow validates the pages and publishes a reviewable artifact for the deployment owner.

## Canonical domain

The canonical public origin is `https://www.sozorock.ca`. The CloudFront distribution serves this hostname through an AWS Certificate Manager certificate in `us-east-1`. DNS routes `www.sozorock.ca` to the CloudFront distribution domain name emitted by the stack. The hosting reference region is AWS Canada Central (`ca-central-1`).

## AWS hosting contract

`infra/public-site.template.json` defines a private S3 origin and a CloudFront distribution. The template enforces S3 public-access blocking, bucket encryption, object ownership, versioning, HTTPS redirection, and GET/HEAD-only delivery. The deployment reference region is AWS Canada Central (`ca-central-1`).

The template does not create learner databases, intake endpoints, model endpoints, credentials, or communication services. Learner services remain disabled in `config/deployment.yaml`.

## Automated publication

After the one-time AWS bootstrap, a push to `main` runs the validation workflow and, when publication is enabled, the deployment workflow. The workflow uses GitHub OIDC to assume `SozoRockCanadaPublicSiteDeploy` in AWS account `891377012881`, locates or requests an ACM certificate in `us-east-1`, deploys the CloudFormation stack in `ca-central-1`, synchronizes `site/` to S3, waits for CloudFront invalidation, and updates the `www.sozorock.ca` CNAME in Route 53.

Long-lived IAM user keys do not enter the repository or GitHub. The approved administrator session is used for the OIDC provider and deployment-role bootstrap.

## Repository activation

The repository variable `PUBLIC_SITE_BUCKET_NAME` identifies the dedicated private S3 bucket. The repository variable `PUBLIC_SITE_DEPLOYMENT_ENABLED` activates automatic publication after the AWS bootstrap is complete. The deployment role ARN is fixed to `arn:aws:iam::891377012881:role/SozoRockCanadaPublicSiteDeploy`.

The bootstrap template is `infra/github-oidc-deploy-role.template.json`. Its stack output supplies the role ARN. The role trust policy accepts the `main` branch of `drolu-cmyk/on-bc-canada`.

One-time bootstrap command:

```bash
aws cloudformation deploy \
  --region ca-central-1 \
  --stack-name sozorock-ca-github-oidc \
  --template-file infra/github-oidc-deploy-role.template.json \
  --parameter-overrides \
    GitHubOwner=drolu-cmyk \
    GitHubRepository=on-bc-canada \
    GitHubBranch=main \
    PublicSiteBucketName=sozorock-ca-public-site-891377012881
```

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
