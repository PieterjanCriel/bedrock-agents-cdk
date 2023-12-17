import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import { CfnOutput, CustomResource, Duration, Stack, custom_resources } from "aws-cdk-lib";
import { PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Architecture, Code, Function, Runtime } from "aws-cdk-lib/aws-lambda";
import { RetentionDays } from "aws-cdk-lib/aws-logs";
import { timeStamp } from "console";
import { Construct } from "constructs";
import path = require("path");

export interface ActionGroup {
    readonly actionGroupName: string;
    readonly actionGroupExecutor: string;
    readonly s3BucketName: string;
    readonly s3ObjectKey: string;
    readonly description?: string;
  }

export interface BedrockAgentProps {
    bedrockRegion: string;
    agentName: string;
    instruction: string;
    foundationModel: string;
    agentResourceRoleArn?: string;
    description?: string;
    idleSessionTTLInSeconds: number;
    actionGroups: ActionGroup[];
}

export class BedrockAgent extends Construct {

    readonly bedrockRegion: string;
    readonly region: string;
    readonly agentName: string;
    readonly instruction: string;
    readonly foundationModel: string;
    readonly agentResourceRoleArn?: string;
    readonly description: string | undefined;
    readonly idleSessionTTLInSeconds: number;
    readonly bedrockAgentCustomResourceRole: Role;
    readonly actionGroups: ActionGroup[];
    readonly physicalResourceId: string;

    constructor(scope: Construct, id: string, props: BedrockAgentProps) {
        super(scope, id);
        this.bedrockRegion = props.bedrockRegion;
        this.region = Stack.of(this).region;
        this.agentName = props.agentName;
        this.instruction = props.instruction;
        this.foundationModel = props.foundationModel;
        this.agentResourceRoleArn = props.agentResourceRoleArn ?? this.getDefaultAgentResourceRoleArn();
        this.description = props.description;
        this.idleSessionTTLInSeconds = props.idleSessionTTLInSeconds;
        this.actionGroups = props.actionGroups;
        
        this.bedrockAgentCustomResourceRole = new Role(this, 'BedrockAgentCustomResourceRole', {
          assumedBy: new ServicePrincipal('lambda.amazonaws.com'),
        });

        this.bedrockAgentCustomResourceRole.addToPolicy(new PolicyStatement({
          actions: ['iam:PassRole'],
          resources: [this.agentResourceRoleArn],
        }));

        this.bedrockAgentCustomResourceRole.addToPolicy(new PolicyStatement({
          actions: ['*'],
          resources: ['arn:aws:bedrock:*'],
        }));

        this.actionGroups.forEach(actionGroup => actionGroup.actionGroupExecutor != 'Undefined' ?
            this.lambdaAttachResourceBasedPolicy(actionGroup.actionGroupExecutor) : 'Undefined');

        const onEvent = new PythonFunction(this, 'BedrockAgentCustomResourceFunction', {
            runtime: Runtime.PYTHON_3_10,
            index: 'index.py',
            handler: 'on_event',
            description: 'Custom resource to create a Bedrock agent.',
            entry: path.join(__dirname, '..', '..', 'lambda', 'BedrockAgentCustomResource'),
            timeout: Duration.seconds(600),
            environment: {
              BEDROCK_REGION: this.bedrockRegion,
              AGENT_NAME: this.agentName,
              INSTRUCTION: this.instruction,
              FOUNDATION_MODEL: this.foundationModel,
              AGENT_RESOURCE_ROLE_ARN: this.agentResourceRoleArn,
              DESCRIPTION: this.description ?? 'Undefined',
              IDLE_SESSION_TTL_IN_SECONDS: this.idleSessionTTLInSeconds.toString(),
              ACTION_GROUPS: JSON.stringify(this.actionGroups),
            },
            role: this.bedrockAgentCustomResourceRole,
            logRetention: RetentionDays.ONE_DAY,
          });

      
          const bedrockAgentCustomResourceProvider = new custom_resources.Provider(this, 'BedrockAgentCustomResourceProvider', {
            onEventHandler: onEvent,
            logRetention: RetentionDays.ONE_DAY,
          });
      
          const customResource = new CustomResource(this, 'BedrockAgentCustomResource', {
            serviceToken: bedrockAgentCustomResourceProvider.serviceToken,
            properties: {
              AgentName: this.agentName,
              Instruction: this.instruction,
              FoundationModel: this.foundationModel,
              AgentResourceRoleArn: this.agentResourceRoleArn,
              Description: this.description ?? 'Undefined',
              IdleSessionTTLInSeconds: this.idleSessionTTLInSeconds,
              ActionGroups: JSON.stringify(this.actionGroups),
            },
          });

          this.physicalResourceId = customResource.getAttString('PhysicalResourceId');

          
    }

    private getDefaultAgentResourceRoleArn(): string {
      return new Role(this, 'AgentIamRole', {
        roleName: 'AmazonBedrockExecutionRoleForAgents_' + this.agentName,
        assumedBy: new ServicePrincipal('bedrock.amazonaws.com'),
        description: 'Agent role created by CDK.',
      }).roleArn;
    }

    private lambdaAttachResourceBasedPolicy(actionGroupExecutor: string): void {
      this.bedrockAgentCustomResourceRole.addToPolicy(new PolicyStatement({
        actions: ['lambda:AddPermission', 'lambda:GetFunction', 'lambda:RemovePermission'],
        resources: [actionGroupExecutor],
      }));
    }
}