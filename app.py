#!/usr/bin/env python3
import os
import boto3

from aws_cdk import core as cdk

from miniwdl_gwfcore_studio.miniwdl_gwfcore_studio_stack import (
    MiniwdlGwfcoreStudioStack,
)

# DEFAULT_GWFCORE_VERSION = "v3.1.0"
# gwfcore_version = os.environ.get("GWFCORE_VERSION", DEFAULT_GWFCORE_VERSION)

env = {}
if "CDK_DEFAULT_ACCOUNT" in os.environ:
    env["account"] = os.environ["CDK_DEFAULT_ACCOUNT"]
if "CDK_DEFAULT_REGION" in os.environ:
    env["region"] = os.environ["CDK_DEFAULT_REGION"]

###################################################################################################
# First perform some ops that aren't convenient to do via CDK/Cfn for various reasons.
###################################################################################################

# Describe existing studio domain+user for VPC/IAM/EFS details
studio_domain_id = os.environ.get("STUDIO_DOMAIN_ID", None)
studio_user_profile_names = os.environ.get("STUDIO_USER_PROFILE_NAME", None).split(",")
assert (
    studio_domain_id and studio_user_profile_names
), "set environment STUDIO_DOMAIN_ID and STUDIO_USER_PROFILE_NAME to reflect SageMaker Studio"
client_opts = {}
if "region" in env:
    client_opts["region_name"] = env["region"]
sagemaker = boto3.client("sagemaker", **client_opts)
domain_desc = sagemaker.describe_domain(DomainId=studio_domain_id)
if studio_user_profile_names == ["*"]:
    lup = sagemaker.list_user_profiles(DomainIdEquals=studio_domain_id, MaxResults=100)
    assert "NextToken" not in lup  # TODO paginate query for >100 users
    studio_user_profile_names = [
        up["UserProfileName"] for up in lup["UserProfiles"] if up["Status"] == "InService"
    ]
user_profile_desc = dict(
    (nm, sagemaker.describe_user_profile(DomainId=studio_domain_id, UserProfileName=nm))
    for nm in studio_user_profile_names
)

#
# Get sst's ssm params
#

ssm = boto3.client("ssm", **client_opts)
stage = ssm.get_parameter(Name="/sst/shire-app/stage")["Parameter"]["Value"]
studio_fsx_id = ssm.get_parameter(Name=f"/sst/shire-app/{stage}/STUDIO_FSX_ID")["Parameter"]["Value"]
studio_fsx_sg_id = ssm.get_parameter(Name=f"/sst/shire-app/{stage}/FSX_SG_ID")["Parameter"]["Value"]
batch_sg_id = ssm.get_parameter(Name=f"/sst/shire-app/{stage}/BATCH_SG_ID")["Parameter"]["Value"]

# ec2 = boto3.client("ec2", **client_opts)
# sg_desc = ec2.describe_security_groups(
#     Filters=[
#         dict(
#             Name="group-name",
#             Values=[f"security-group-for-inbound-nfs-{studio_domain_id}"],
#         )
#     ]
# )
# assert (
#     len(sg_desc.get("SecurityGroups", [])) == 1
# ), f"Failed to look up SageMaker Studio FSx security group named 'security-group-for-inbound-nfs-{studio_domain_id}'"
# studio_fsx_sg_id = sg_desc["SecurityGroups"][0]["GroupId"]

# Log the detected details
print(f"studio_domain_id = {studio_domain_id}")
print(f"studio_user_profile_name = {','.join(studio_user_profile_names)}")
print(f"studio_fsx_id = {studio_fsx_id}")
print(f"studio_fsx_sg_id = {studio_fsx_sg_id}")
print(f"vpc_id = {domain_desc['VpcId']}")
print(f"batch_sg_id = {batch_sg_id}")
# probably don't need uids?

# detected = dict(
    # vpc_id=domain_desc["VpcId"],
    # studio_fsx_id=domain_desc["HomeFsxFileSystemId"],
    # studio_fsx_uids=list(
        # set(user_profile_desc[nm]["HomeFsxFileSystemUid"] for nm in user_profile_desc)
    # ),
    # studio_fsx_sg_id=studio_fsx_sg_id,
# )
# for k, v in detected.items():
#     print(f"{k} = {v}")

# Add necessary policies to the Studio ExecutionRole. We don't do this through CDK because of:
#   https://github.com/aws/aws-cdk/blob/486f2e5518ab5abb69a3e3986e4f3581aa42d15b/packages/%40aws-cdk/aws-iam/lib/role.ts#L225-L227
iam = boto3.client("iam", **client_opts)
for studio_execution_role_arn in set(
    user_profile_desc[nm].get("UserSettings", {}).get("ExecutionRole", "")
    for nm in user_profile_desc
):
    assert studio_execution_role_arn.startswith(
        "arn:aws:iam::"
    ), "Failed to detect SageMaker Studio ExecutionRole ARN"
    studio_execution_role_name = studio_execution_role_arn[
        studio_execution_role_arn.rindex("/") + 1 :
    ]

    for policy_arn in (
        "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess",
        "arn:aws:iam::aws:policy/AWSBatchFullAccess",
        "arn:aws:iam::aws:policy/AmazonElasticFileSystemFullAccess",
    ):
        # TODO: constrain these to the specific EFS & Batch queues
        print(f"Adding to {studio_execution_role_name}: {policy_arn}")
        iam.attach_role_policy(
            RoleName=studio_execution_role_arn[studio_execution_role_arn.rindex("/") + 1 :],
            PolicyArn=policy_arn,
        )


###################################################################################################
# CDK stack to do the rest
###################################################################################################


app = cdk.App()
MiniwdlGwfcoreStudioStack(
    app,
    "MiniwdlGwfcoreStudioStack",
    # gwfcore_version=gwfcore_version,
    env=env,
    studio_fsx_id=studio_fsx_id,
    studio_fsx_sg_id=studio_fsx_sg_id,
    vpc_id=domain_desc["VpcId"],
    batch_sg_id=batch_sg_id,
    # **detected,
)

app.synth()
