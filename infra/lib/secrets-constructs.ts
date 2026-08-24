import * as cdk from 'aws-cdk-lib';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

export interface SecretsConstructProps {
  appName: string;
}

export class SecretsConstruct extends Construct {
  public readonly apiKeySecret: secretsmanager.Secret;
  public readonly workerKeySecret: secretsmanager.Secret;

  constructor(scope: Construct, id: string, props: SecretsConstructProps) {
    super(scope, id);

    this.apiKeySecret = new secretsmanager.Secret(this, 'ApiKeySecret', {
      secretName: `${props.appName}/api-key`,
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ service: 'api' }),
        generateStringKey: 'key',
      },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    this.workerKeySecret = new secretsmanager.Secret(this, 'WorkerKeySecret', {
      secretName: `${props.appName}/worker-key`,
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ service: 'worker' }),
        generateStringKey: 'key',
      },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
  }
}
