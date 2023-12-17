import boto3
import os
import time
import json

agent_name = os.environ['AGENT_NAME']
instruction = os.environ['INSTRUCTION']
foundation_model = os.environ['FOUNDATION_MODEL']
agent_resource_role_arn = os.environ['AGENT_RESOURCE_ROLE_ARN']
agent_description = os.environ['DESCRIPTION']
agent_session_timeout = os.environ['IDLE_SESSION_TTL_IN_SECONDS']
action_group_parameters_list = json.loads(os.environ['ACTION_GROUPS'])
region = os.environ['AWS_REGION']
bedrock_region = os.environ['BEDROCK_REGION']

agent_client = boto3.client("bedrock-agent", region_name=bedrock_region)
lambda_client = boto3.client("lambda")

def on_event(event, context):
    account_id = context.invoked_function_arn.split(":")[4]
    physical_id = f"BedrockAgent-{agent_name}-cdk"
    request_type = event['RequestType']

    if request_type == 'Create':
        return on_create(event,
                         agent_name=agent_name,
                         instruction=instruction,
                         foundation_model=foundation_model,
                         agent_resource_role_arn=agent_resource_role_arn,
                         agent_description=agent_description,
                         agent_session_timeout=agent_session_timeout,
                         action_group_parameters_list=action_group_parameters_list,
                         physical_id=physical_id,
                         region=region,
                         account_id=account_id)
    if request_type == 'Update':
        return on_update(event,
                         physical_id=physical_id,
                         account_id=account_id)
    if request_type == 'Delete':
        return on_delete(event,
                         agent_name=agent_name,
                         physical_id=physical_id)
    raise Exception("Invalid request type: %s" % request_type)

def on_create(event,
              agent_name,
              instruction,
              foundation_model,
              agent_resource_role_arn,
              agent_description,
              agent_session_timeout,
              action_group_parameters_list,
              physical_id,
              region,
              account_id):

    props = event["ResourceProperties"]

    agent_id = create_agent(agent_name=agent_name,
                            agent_resource_role_arn=agent_resource_role_arn,
                            foundation_model=foundation_model,
                            agent_description=agent_description,
                            agent_session_timeout=agent_session_timeout,
                            instruction=instruction)
    # Pause to make sure agents has been created
    time.sleep(15)
    for action_group_parameters in action_group_parameters_list:
        if action_group_parameters['s3BucketName'] != 'Undefined':

            action_group_name = action_group_parameters['actionGroupName']
            lambda_arn = action_group_parameters['actionGroupExecutor']
            s3_bucket_name = action_group_parameters['s3BucketName']
            s3_bucket_key = action_group_parameters['s3ObjectKey']
            action_group_description = action_group_parameters.get(
                'description', 'Undefined')

            lambda_add_agent_permission(agent_id=agent_id,
                                        agent_name=agent_name,
                                        function_name=lambda_arn,
                                        region=region,
                                        account_id=account_id)
            # Pause to make sure policy was attached
            time.sleep(10)

            create_agent_action_group(action_group_name=action_group_name,
                                      lambda_arn=lambda_arn,
                                      bucket_name=s3_bucket_name,
                                      key=s3_bucket_key,
                                      action_group_description=action_group_description,
                                      agent_id=agent_id)

    
    return {'PhysicalResourceId': physical_id}

def on_update(event, physical_id, account_id):
    props = event["ResourceProperties"]
    agent_name = props["AgentName"]
    agent_resource_role_arn = props["AgentResourceRoleArn"]
    foundation_model = props["FoundationModel"]
    description = props["Description"]
    idle_session_ttl_in_seconds = props["IdleSessionTTLInSeconds"]
    instruction = props["Instruction"]
    action_groups = json.loads(props["ActionGroups"])

    agent_list = agent_client.list_agents()
    for entry in agent_list['agentSummaries']:
        if entry['agentName'] == agent_name:
            agent = entry
            break

    agent_id = agent['agentId']

    update_agent(agent_id=agent_id,
                 agent_name=agent_name,
                 agent_resource_role_arn=agent_resource_role_arn,
                 foundation_model=foundation_model,
                 agent_description=description,
                 agent_session_timeout=idle_session_ttl_in_seconds,
                 instruction=instruction)

    # get existing action groups
    existing_action_groups = agent_client.list_agent_action_groups(agentId=agent_id,
                                                                   agentVersion='DRAFT')
    
    if 'actionGroupSummaries' in existing_action_groups:
        existing_action_groups = existing_action_groups['actionGroupSummaries']
    else:
        existing_action_groups = []

    # get action groups details
    existing_action_groups_details = []
    for action_group in existing_action_groups:
        action_group_details = agent_client.get_agent_action_group(agentId=agent_id,
                                                                   agentVersion='DRAFT',
                                                                   actionGroupId=action_group['actionGroupId'])
        existing_action_groups_details.append(action_group_details['agentActionGroup'])

    existing_action_groups_details_map = {}
    for action_group in existing_action_groups_details:
        existing_action_groups_details_map[action_group['actionGroupName']] = action_group

    # get action grooups from props
    action_group_map = {}
    for action_group in action_groups:
        action_group_map[action_group['actionGroupName']] = action_group

    # actions groups names in the props but not in the existing action groups
    action_groups_to_create = set(action_group_map.keys()) - set(existing_action_groups_details_map.keys())
    print(f"Action groups to create: {action_groups_to_create}")

    for action_group_name in action_groups_to_create:
        lambda_arn = action_group_map[action_group_name]['actionGroupExecutor']
        s3_bucket_name = action_group_map[action_group_name]['s3BucketName']
        s3_bucket_key = action_group_map[action_group_name]['s3ObjectKey']
        action_group_description = action_group_map[action_group_name].get('description', 'Undefined')

        lambda_add_agent_permission(agent_id=agent_id,
                                    agent_name=agent_name,
                                    function_name=lambda_arn,
                                    region=region,
                                    account_id=account_id)
        # Pause to make sure policy was attached
        time.sleep(10)

        create_agent_action_group(action_group_name=action_group_name,
                                  lambda_arn=lambda_arn,
                                  bucket_name=s3_bucket_name,
                                  key=s3_bucket_key,
                                  action_group_description=action_group_description,
                                  agent_id=agent_id)

    # action groups names in the existing action groups but not in the props
    action_groups_to_delete = set(existing_action_groups_details_map.keys()) - set(action_group_map.keys())
    print(f"Action groups to delete: {action_groups_to_delete}")

    for action_group_name in action_groups_to_delete:
        delete_agent_action_group(agent_id=agent_id,
                                  agent_version='DRAFT',
                                  action_group_id=existing_action_groups_details_map[action_group_name]['actionGroupId'],
                                  skipResourceInUseCheck=True)
        print(f"Deleted action group: {action_group_name}")

    # action groups names in both the props and the existing action groups
    action_groups_to_update = set(action_group_map.keys()) & set(existing_action_groups_details_map.keys())
    print(f"Action groups to check for update: {action_groups_to_update}")

    for action_group_name in action_groups_to_update:
        # check if action group details are different based on the name, function arn, s3 bucket name and s3 key
        if action_group_map[action_group_name]['actionGroupExecutor'] == existing_action_groups_details_map[action_group_name]['actionGroupExecutor']['lambda'] and \
            action_group_map[action_group_name]['s3BucketName'] == existing_action_groups_details_map[action_group_name]['apiSchema']['s3']['s3BucketName'] and \
            action_group_map[action_group_name]['s3ObjectKey'] == existing_action_groups_details_map[action_group_name]['apiSchema']['s3']['s3ObjectKey'] and \
            action_group_map[action_group_name].get('description', 'Undefined') == existing_action_groups_details_map[action_group_name].get('description', 'Undefined'):
            print(f"Action group {action_group_name} is up to date")
            continue
        
        lambda_arn = action_group_map[action_group_name]['actionGroupExecutor']
        s3_bucket_name = action_group_map[action_group_name]['s3BucketName']
        s3_bucket_key = action_group_map[action_group_name]['s3ObjectKey']
        action_group_description = action_group_map[action_group_name].get('description', 'Undefined')
        action_group_id = existing_action_groups_details_map[action_group_name]['actionGroupId']

        update_agent_action_group(agent_id=agent_id,
                                  lambda_arn=lambda_arn,
                                  bucket_name=s3_bucket_name,
                                  key=s3_bucket_key,
                                  action_group_id=action_group_id,
                                  action_group_description=action_group_description,
                                  action_group_name=action_group_name,
                                  agent_version='DRAFT',
                                  action_group_state='ENABLED')
        print(f"Updated action group: {action_group_name}")

    return {'PhysicalResourceId': physical_id}


def on_delete(event, 
              agent_name, 
              physical_id):
    delete_agent(agent_name=agent_name)

    return {'PhysicalResourceId': physical_id}

def create_agent(agent_name,
                 agent_resource_role_arn,
                 foundation_model,
                 agent_description,
                 agent_session_timeout,
                 instruction):

    args = {
        'agentName': agent_name,
        'agentResourceRoleArn': agent_resource_role_arn,
        'foundationModel': foundation_model,
        'idleSessionTTLInSeconds': int(agent_session_timeout),
        'instruction': instruction,
        'description': agent_description
    }

    if args['description'] == 'Undefined':
        args.pop('description')

    response = agent_client.create_agent(**args)

    return response['agent']['agentId']

def update_agent(agent_id,
                 agent_name,
                 agent_resource_role_arn,
                 foundation_model,
                 agent_description,
                 agent_session_timeout,
                 instruction):
    
    # try to cast agent_session_timeout to int, else set to None
    try:
        agent_session_timeout = int(agent_session_timeout)
    except ValueError:
        agent_session_timeout = None
    
    args = {
        'agentId': agent_id,
        'agentName': agent_name,
        'agentResourceRoleArn': agent_resource_role_arn,
        'foundationModel': foundation_model,
        'idleSessionTTLInSeconds': int(agent_session_timeout),
        'instruction': instruction,
        'description': agent_description
    }

    if args['description'] == 'Undefined':
        args.pop('description')

    if args['idleSessionTTLInSeconds'] == None:
        args.pop('idleSessionTTLInSeconds')

    return agent_client.update_agent(**args)

def delete_agent(agent_name):
    # Get list of all agents
    response = agent_client.list_agents()
    # Find agent with the given name
    for agent in response["agentSummaries"]:
        if agent["agentName"] == agent_name:
            agent_id = agent["agentId"]
            return agent_client.delete_agent(agentId=agent_id)
    
    return None

def delete_agent_action_group(agent_id, action_group_id):
    return agent_client.delete_agent_action_group(agentId=agent_id,
                                                  agentVersion='DRAFT',
                                                  actionGroupId=action_group_id,
                                                  skipResourceInUseCheck=True)

def create_agent_action_group(agent_id,
                              lambda_arn,
                              bucket_name,
                              key,
                              action_group_description,
                              action_group_name):

    args = {
        'agentId': agent_id,
        'actionGroupExecutor': {
            'lambda': lambda_arn,
        },
        'actionGroupName': action_group_name,
        'agentVersion': 'DRAFT',
        'apiSchema': {
            's3': {
                's3BucketName': bucket_name,
                's3ObjectKey': key
            }
        },
        'description': action_group_description
    }

    if args['description'] == 'Undefined':
        args.pop('description')

    return agent_client.create_agent_action_group(**args)


def update_agent_action_group(agent_id,
                              lambda_arn,
                              bucket_name,
                              key,
                              action_group_id,
                              action_group_description,
                              action_group_name,
                              agent_version='DRAFT',
                              action_group_state='ENABLED'):
        
        args = {
            'agentId': agent_id,
            'actionGroupExecutor': {
                'lambda': lambda_arn,
            },
            'actionGroupId': action_group_id,
            'actionGroupName': action_group_name,
            'agentVersion': agent_version,
            'actionGroupState': action_group_state,
            'apiSchema': {
                's3': {
                    's3BucketName': bucket_name,
                    's3ObjectKey': key
                }
            },
            'description': action_group_description
        }
    
        if args['description'] == 'Undefined':
            args.pop('description')
    
        return agent_client.update_agent_action_group(**args)

def lambda_add_agent_permission(agent_name, function_name,
                                region, account_id, agent_id):

    try:
        lambda_client.add_permission(
          FunctionName=function_name,
          StatementId=f'allowInvoke-{agent_name}',
          Action='lambda:InvokeFunction',
          Principal='bedrock.amazonaws.com',
          SourceArn=f"arn:aws:bedrock:{region}:{account_id}:agent/{agent_id}",
        )
    except lambda_client.exceptions.ResourceConflictException:
        pass