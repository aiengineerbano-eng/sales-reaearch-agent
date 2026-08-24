import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecsPatterns from 'aws-cdk-lib/aws-ecs-patterns';
import { Construct } from 'constructs';

export interface EcsServiceProps {
  appName: string;
  vpc: ec2.Vpc;
  cpu?: number;
  memoryLimitMiB?: number;
}

export class ApiServiceConstruct extends Construct {
  public readonly cluster: ecs.Cluster;
  public readonly service: ecsPatterns.ApplicationLoadBalancedFargateService;

  constructor(scope: Construct, id: string, props: EcsServiceProps) {
    super(scope, id);

    this.cluster = new ecs.Cluster(this, 'Cluster', {
      clusterName: `${props.appName}-cluster`,
      vpc: props.vpc,
    });

    const repository = ecr.Repository.fromRepositoryName(this, 'ApiRepo', `${props.appName}-api`);

    this.service = new ecsPatterns.ApplicationLoadBalancedFargateService(this, 'ApiService', {
      cluster: this.cluster,
      desiredCount: 1,
      cpu: props.cpu ?? 512,
      memoryLimitMiB: props.memoryLimitMiB ?? 1024,
      taskImageOptions: {
        image: ecs.ContainerImage.fromEcrRepository(repository, 'latest'),
        containerPort: 8000,
        environment: {
          APP_NAME: props.appName,
        },
      },
      publicLoadBalancer: true,
    });

    this.service.targetGroup.configureHealthCheck({
      path: '/health',
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
      interval: cdk.Duration.seconds(30),
    });
  }
}
