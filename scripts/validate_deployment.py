#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 errors=[]
 pub=json.loads((ROOT/'infra/public-site.template.json').read_text())
 eng=json.loads((ROOT/'infra/engagement-backend.template.json').read_text())
 r=pub.get('Resources',{}); code=r.get('CanonicalRouteFunction',{}).get('Properties',{}).get('FunctionCode','')
 for x in ('/index.html','/program.html','/stories.html','/insights','/enroll.html','/register-interest',"r.uri=u+'.html'"):
  if x not in code:errors.append(f'canonical route function missing {x}')
 config=r.get('PublicSiteDistribution',{}).get('Properties',{}).get('DistributionConfig',{})
 if config.get('IPV6Enabled') is not True:errors.append('CloudFront IPv6 must be enabled')
 if config.get('ViewerCertificate',{}).get('MinimumProtocolVersion')!='TLSv1.2_2021':errors.append('CloudFront TLS policy must be TLSv1.2_2021')
 if config.get('Aliases',{}).get('Fn::If')!=['PublishCustomDomain',[{'Ref':'CanonicalDomainName'}],{'Ref':'AWS::NoValue'}]:errors.append('CloudFront may attach only canonical alias')
 er=eng.get('Resources',{})
 required={'SubmissionsTable':'AWS::DynamoDB::Table','NotificationTopic':'AWS::SNS::Topic','AdminUserPool':'AWS::Cognito::UserPool','EngagementFunction':'AWS::Lambda::Function','Api':'AWS::ApiGatewayV2::Api','AdminAuthorizer':'AWS::ApiGatewayV2::Authorizer'}
 for n,t in required.items():
  if er.get(n,{}).get('Type')!=t:errors.append(f'engagement backend missing {n}={t}')
 if eng.get('Parameters',{}).get('AllowedOrigin',{}).get('Default')!='https://canada.sozorock.com':errors.append('engagement API origin must be canonical Canada site')
 if eng.get('Parameters',{}).get('NotificationEmail',{}).get('Default')!='oluview@gmail.com':errors.append('notification email default is incorrect')
 if errors:
  print('Deployment validation failed:',file=sys.stderr);print('\n'.join(errors),file=sys.stderr);return 1
 print('Deployment validation passed for canonical site and engagement backend.');return 0
if __name__=='__main__':raise SystemExit(main())
