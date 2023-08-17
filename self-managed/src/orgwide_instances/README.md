# OrgWide EC2 Instance Data Aggregation

With these scripts, you can collect EC2 Instance data across your entire
AWS Organization. 
## Requirements
Before using the workflow, certain permissions need to be provisioned to both 
the management/delegated admin account and member accounts.
#### Management/Delegated Admin Permissions
The role assumed in the management/delegated admin account must have permissions to call 
the following APIs:
- Cloudformation - CreateStackSet, CreateStackInstance, DetectStackSetDrift, DescribeStackSetOperation
- Organizations - ListAllAccounts, ListRoots, ListDelegatedAdministrators
- STS - AssumeRole, GetCallerIdentity
#### Member Account Permissions
The role assumed in the member accounts must have permissions to the following APIs:
- EC2 - DescribeInstances, DescribeRegions
- SSM - DescribeInstanceInformation  

This role must have the management/delegated admin as a trusted entity to assume
this role.

## How to Use the Workflow
### Inputs
The inputs to the program can be altered in "orgwide_instance_inputs". These are
the following inputs provided.
- source_regions: _[string]_ - List of regions to gather data from. If left empty, workflow
will gather all ec2_instance data from regions that each member account is active in. 
- org_wide_role_name: _string_ - Name of role present in member accounts. Management/Delegated 
Admin account will assume this role to make necessary calls
- default_region: _string_ - Used to determine which region to deploy stack set. Only
used if "automatic_member_role_creation" is set to True
- stack_set_name: _string_ - Desired name of management account stack set. Only used
if "automatic_member_role_creation" is set to True
- automatic_member_role_creation: _boolean_ - Set to true if you want automatic 
deployment of roles and policies into member accounts

##### Default inputs
```
{
  "default_region": "us-east-1",
  "source_regions": [],
  "org_wide_role_name": "AdminOrgWideInstancesAggregator",
  "stack_set_name": "OrgWideInstanceAggregatorStackSet",
  "automatic_member_role_creation": true
}
```
### Execution
Simply run the command 
```
python3 orgwide_instance.py
```
