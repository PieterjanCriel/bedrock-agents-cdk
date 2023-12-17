#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { CdkBedrockAgentStack } from '../lib/cdk-bedrock-agent-stack';

const app = new cdk.App();
new CdkBedrockAgentStack(app, 'CdkBedrockAgentStack');
