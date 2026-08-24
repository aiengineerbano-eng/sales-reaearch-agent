import * as cdk from 'aws-cdk-lib';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';

export interface SsmConstructProps {
  appName: string;
  apiUrl?: string;
}

export class SsmConstruct extends Construct {
  public readonly apiUrlParameter: ssm.StringParameter;

  constructor(scope: Construct, id: string, props: SsmConstructProps) {
    super(scope, id);

    this.apiUrlParameter = new ssm.StringParameter(this, 'ApiUrlParameter', {
      parameterName: `/${props.appName}/api/url`,
      stringValue: props.apiUrl ?? 'https://example.invalid',
      description: 'Base URL for the sales research API',
      tier: ssm.ParameterTier.STANDARD,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
  }
}
