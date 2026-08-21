# Public site

Applied AI Training for Canada publishes a static information site for program information, curriculum themes, accessibility, privacy, terms, and participation details.

## What is published

The `site/` directory contains the public pages. The public site has no learner intake, account creation, learner workspace, analytics form, advertising tracker, or external model call.

## Web addresses

The canonical Canada address is:

- https://canada.sozorock.com

The legacy addresses remain available only as permanent redirects:

- https://sozorock.ca
- https://www.sozorock.ca

Both legacy hosts preserve the requested path and query string when redirecting to `https://canada.sozorock.com`.

## Hosting

The public site uses a private S3 origin and CloudFront distribution. The application stack remains in AWS Canada Central (`ca-central-1`). The CloudFront certificate is managed in `us-east-1`, as required for CloudFront custom domains.

## Program boundary

The training is free and virtual across Canada. Public participation information does not represent accreditation, a degree, diploma, professional licence, employment guarantee, immigration pathway, study permit pathway, endorsement, affiliation, or competency credential.

## Site quality

The pages include privacy, terms, accessibility information, contact guidance, and a clear participation boundary. Changes to public pages pass content, site, curriculum, and deployment checks before publication.

The public information site is separate from learner operations. The current site collects no learner data.
