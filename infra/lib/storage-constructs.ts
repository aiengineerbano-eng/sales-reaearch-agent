import * as cdk from 'aws-cdk-lib';
import * as ec2  from 'aws-cdk-lib/aws-ec2';
import * as efs  from 'aws-cdk-lib/aws-efs';
import { Construct } from 'constructs';

export interface StorageConstructsProps {
  vpc: ec2.IVpc;
}

export class StorageConstructs extends Construct {
  public readonly fileSystem:    efs.FileSystem;
  public readonly accessPoint:   efs.AccessPoint;
  public readonly efsSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: StorageConstructsProps) {
    super(scope, id);

    // Security group for EFS — only allow NFS from within the VPC
    this.efsSecurityGroup = new ec2.SecurityGroup(this, 'EfsSg', {
      vpc:              props.vpc,
      description:      'EFS access for Sales Agent containers',
      allowAllOutbound: false,
    });

    this.efsSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(props.vpc.vpcCidrBlock),
      ec2.Port.tcp(2049),
      'NFS from VPC',
    );

    // EFS file system — stores SQLite DB shared between API and Worker
    this.fileSystem = new efs.FileSystem(this, 'SalesAgentEfs', {
      vpc:             props.vpc,
      securityGroup:   this.efsSecurityGroup,
      encrypted:       true,
      performanceMode: efs.PerformanceMode.GENERAL_PURPOSE,
      removalPolicy:   cdk.RemovalPolicy.RETAIN, // keep DB on stack destroy
      lifecyclePolicy: efs.LifecyclePolicy.AFTER_30_DAYS,
    });

    // Access point — mounts at /data inside containers
    this.accessPoint = new efs.AccessPoint(this, 'DataAccessPoint', {
      fileSystem: this.fileSystem,
      path:       '/data',
      createAcl: {
        ownerGid: '1000',
        ownerUid: '1000',
        permissions: '755',
      },
      posixUser: {
        gid: '1000',
        uid: '1000',
      },
    });

    new cdk.CfnOutput(this, 'EfsId', {
      value:       this.fileSystem.fileSystemId,
      description: 'EFS file system ID (shared SQLite)',
    });
  }
}