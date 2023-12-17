#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { AgentStack } from '../lib/agentStack';

const env = {
    region: 'us-east-1',
    account: process.env.CDK_DEFAULT_ACCOUNT,
};

const app = new cdk.App();

const agentStack = new AgentStack(app, 'AgentStack', {env});
