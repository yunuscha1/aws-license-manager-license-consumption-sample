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
- Organizations - ListAllAccounts, ListRoots, ListDelegatedAdministrators, ListAccountsForParent
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
- accounts: _[string]_ - List of accounts to gather data from. If this and "ou_ids" are left empty,
all accounts in the organization will have their data collected
- ou_ids: _[string]_ - List of OUs to gather data from. If this and "accounts" are left empty, all
accounts in the organization will have their data collected. 
- org_wide_role_name: _string_ - Name of role present in member accounts. Management/Delegated 
Admin account will assume this role to make necessary calls
- default_region: _string_ - Used to determine which region to deploy stack set. Only
used if "automatic_member_role_creation" is set to True
- stack_set_name: _string_ - Desired name of management account stack set. Only used
if "automatic_member_role_creation" is set to True
- automatic_member_role_creation: _boolean_ - Set to true if you want automatic 
deployment of roles and policies into member accounts
- check_stack_set_status: _boolean_ - Set to true if you would like to check
if any permissions in member accounts have changed. Setting to false will make the 
execution of the script faster.
- custom-product-codes: _dict_ A dictionary used to categorize any custom product codes. The 
name of the product should be a key and any associated product codes should be placed into a list.

Note: Only one of either "accounts" or "ou_ids" may be used at a time.
##### Default inputs
```
{
  "source_regions": [],
  "accounts": [],
  "ou_ids": [],
  "org_wide_role_name": "AdminOrgWideInstancesAggregator",
  "default_region": "us-east-1",
  "stack_set_name": "OrgWideInstanceAggregatorStackSet",
  "automatic_member_role_creation": true,
  "check_stack_set_status": false,
  "custom_product_codes": {"example-product-type": ["Associated-product-code-1", "Associated-product-code-2"]}
}
```
### Execution
Simply run the command 
```
python3 orgwide_instance.py
```
To delete automatically created stack set
```angular2html
python3 orgwide_instance_delete_roles.py
```
### Trusted Policy Template
```angular2html
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::{management/delegated admin #}:root"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
```
### Policy Template
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": [
                "ec2:DescribeInstances",
                "ec2:DescribeRegions",
                "ssm:DescribeInstanceInformation"
            ],
            "Resource": "*",
            "Effect": "Allow"
        }
    ]
}
```