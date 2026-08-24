import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';
import { AuthConstruct } from './auth-construct';
import { ApiServiceConstruct } from './ecs-constructs';
import { FrontendConstruct } from './frontend-constructs';
import { SecretsConstruct } from './secrets-constructs';
import { SsmConstruct } from './ssm-constructs';

export class SalesAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const appName = 'sales-research-agent';

    const vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    const auth = new AuthConstruct(this, 'Auth', {
      appName,
      callbackUrls: ['https://localhost:3000', 'https://localhost:5173'],
      logoutUrls: ['https://localhost:3000', 'https://localhost:5173'],
    });

    const secrets = new SecretsConstruct(this, 'Secrets', {
      appName,
    });

    const apiService = new ApiServiceConstruct(this, 'ApiService', {
      appName,
      vpc,
      cpu: 512,
      memoryLimitMiB: 1024,
    });

    const frontend = new FrontendConstruct(this, 'Frontend', {
      appName,
      buildFolderPath: './ui/dist',
    });

    const ssm = new SsmConstruct(this, 'Ssm', {
      appName,
      apiUrl: `https://${apiService.service.loadBalancer.loadBalancerDnsName}`,
    });

    new cdk.CfnOutput(this, 'UserPoolId', {
      value: auth.userPool.userPoolId,
      description: 'Cognito user pool ID',
    });

    new cdk.CfnOutput(this, 'UserPoolClientId', {
      value: auth.userPoolClient.userPoolClientId,
      description: 'Cognito app client ID',
    });

    new cdk.CfnOutput(this, 'ApiUrl', {
      value: ssm.apiUrlParameter.stringValue,
      description: 'API base URL parameter',
    });

    new cdk.CfnOutput(this, 'FrontendUrl', {
      value: `https://${frontend.distribution.distributionDomainName}`,
      description: 'CloudFront distribution URL',
    });

    new cdk.CfnOutput(this, 'ApiSecretArn', {
      value: secrets.apiKeySecret.secretArn,
      description: 'API secret ARN',
    });
  }
}
