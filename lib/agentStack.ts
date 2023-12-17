import { Duration, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { BedrockAgent, BedrockAgentProps } from './constructs/bedrock_agent_custom_resource';
import { PolicyStatement, Role, ServicePrincipal } from 'aws-cdk-lib/aws-iam';
import { BucketDeployment, Source } from 'aws-cdk-lib/aws-s3-deployment';
import { PythonFunction } from '@aws-cdk/aws-lambda-python-alpha';
import path = require('path');
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { Runtime } from 'aws-cdk-lib/aws-lambda';
import * as fs from 'fs';


export class AgentStack extends Stack {

    constructor(scope: Construct, id: string, props?: StackProps) {
        super(scope, id, props);

        const actiongroupSpecBucket = new Bucket(this, 'ActiongroupSpecBucket', {});

        const openAPISpecJson = fs.readFileSync(path.join(__dirname, '..', 'actions', 'demo-action', 'spec.json'), 'utf8');

        new BucketDeployment(this, 'DeployActiongroup', {
            sources: [Source.jsonData('spec.json', JSON.parse(openAPISpecJson))],
            destinationBucket: actiongroupSpecBucket,
            destinationKeyPrefix: 'actions/demo-action/'
        });

        const demoActionFunction = new PythonFunction(this, 'ActiongroupFunction', {
            entry: path.join(__dirname, '..', 'actions', 'demo-action'),
            index: 'index.py',
            handler: 'lambda_handler',
            runtime: Runtime.PYTHON_3_10,
            timeout: Duration.seconds(30),
        });


        const agentRole = new Role(this, 'AgentIamRole', {
            roleName: 'AmazonBedrockExecutionRoleForAgents_' + 'knock-knock-agent',
            assumedBy: new ServicePrincipal('bedrock.amazonaws.com'),
            description: 'Agent role created by CDK.',
          })

        agentRole.addToPolicy(new PolicyStatement({
            actions: ['*'],
            resources: ['arn:aws:bedrock:*'],
        }));

        actiongroupSpecBucket.grantRead(agentRole);

        const bedrockAgentProps: BedrockAgentProps = {
            bedrockRegion: 'us-east-1',
            agentName: 'knock-knock-agent',
            instruction: 'you are an agent that helps a user to check if numbers have certain properties. e.g if a number is prime. You use action groups for these tasks',
            foundationModel: 'anthropic.claude-v2',
            agentResourceRoleArn: agentRole.roleArn,
            description: 'knock-knock-agent',
            idleSessionTTLInSeconds: 600,
            actionGroups: [{
                actionGroupName: 'demo-action',
                actionGroupExecutor: demoActionFunction.functionArn,
                s3BucketName: actiongroupSpecBucket.bucketName,
                s3ObjectKey: 'actions/demo-action/spec.json',
                description: 'Demo action group',
                }]
        };

        new BedrockAgent(this, 'BedrockAgent', bedrockAgentProps);
    }
}