import os
import tempfile
import boto3
# from typing import List
from contextlib import ExitStack
from aws_cdk import (
    core as cdk,
    cloudformation_include as cdk_cfn_inc,
    aws_ec2 as cdk_ec2,
    aws_iam as cdk_iam,
    aws_fsx as cdk_fsx,
)


class MiniwdlGwfcoreStudioStack(cdk.Stack):
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        *,
        vpc_id: str,
        studio_fsx_id: str,
        # studio_fsx_uids: List[str],
        studio_fsx_sg_id: str,
        batch_sg_id: str,
        # gwfcore_version: str = "latest",
        env,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, env=env, **kwargs)

        # Prepare temp dir
        self._cleanup = ExitStack()
        self._tmpdir = self._cleanup.enter_context(tempfile.TemporaryDirectory())

        # Detect VPC subnets
        vpc = cdk_ec2.Vpc.from_lookup(self, "Vpc", vpc_id=vpc_id)
        subnet_ids = vpc.select_subnets(subnet_type=cdk_ec2.SubnetType.PUBLIC).subnet_ids

        # get batch security group
        batch_sg = cdk_ec2.SecurityGroup.from_security_group_id(
            self,
            "BatchSecurityGroup",
            batch_sg_id,
        )

        # Modify Studio EFS security group to allow access from gwfcore's Batch compute environment
        studio_fsx_sg = cdk_ec2.SecurityGroup.from_security_group_id(
            self, "StudioFSxSecurityGroup", studio_fsx_sg_id
        )
        studio_fsx_sg.add_ingress_rule(batch_sg, cdk_ec2.Port.tcp(2049))

        # Add EFS Access Point to help Batch jobs "see" the user's EFS directory in the same way
        # SageMaker Studio presents it. Inside Studio, miniwdl-aws can detect this by filtering
        # access points for the correct EFS ID, uid, and path.
        # studio_fsx = cdk_fsx.FileSystem.from_file_system_attributes(
        #     self,
        #     "StudioFSX",
        #     file_system_id=studio_fsx_id,
        #     security_group=studio_fsx_sg,
        # )
        # for uid in studio_fsx_uids:
        #     cdk_efs.AccessPoint(
        #         self,
        #         f"StudioFSAPuid{uid}x",
        #         file_system=studio_efs,
        #         posix_user=cdk_efs.PosixUser(uid=uid, gid=uid),
        #         path=f"/{uid}",
        #     )

    def __del__(self):
        # clean up temp dir
        if self._cleanup:
            try:
                self._cleanup.close()
            except:
                pass

    # def _gwfcore(self, version, vpc_id, subnet_ids, studio_fsx_id, env):
    #     # Import gwfcore CloudFormation templates from the aws-genomics-workflows S3 bucket
    #     s3 = boto3.client("s3", region_name="us-east-1")

    #     def _template(basename):
    #         # CfnInclude needs a local filename, so download template to temp dir
    #         tfn = os.path.join(self._tmpdir, basename)
    #         s3.download_file(
    #             "aws-genomics-workflows", f"{version}/templates/gwfcore/{basename}", tfn
    #         )
    #         return tfn

    #     cfn_gwfcore = cdk_cfn_inc.CfnInclude(
    #         self,
    #         "gwfcore",
    #         template_file=_template("gwfcore-root.template.yaml"),
    #         load_nested_stacks=dict(
    #             (s, {"templateFile": _template(fn)})
    #             for (s, fn) in (
    #                 ("BatchStack", "gwfcore-batch.template.yaml"),
    #                 ("S3Stack", "gwfcore-s3.template.yaml"),
    #                 ("IamStack", "gwfcore-iam.template.yaml"),
    #                 ("CodeStack", "gwfcore-code.template.yaml"),
    #                 ("LaunchTplStack", "gwfcore-launch-template.template.yaml"),
    #             )
    #         ),
    #         parameters={
    #             "VpcId": vpc_id,
    #             "SubnetIds": subnet_ids,
    #             "NumberOfSubnets": len(subnet_ids),
    #             "S3BucketName": f"minwidl-gwfcore-studio-{env['account']}-{env['region']}",
    #             "BatchComputeInstanceTypes": "m5,m5n,c5,c5n,r5,r5n,r5b",
    #         },
    #     )

    #     # Add EFS client access policy to the Batch instance role
    #     included_gwfcore_iam_stack = cfn_gwfcore.get_nested_stack("IamStack")
    #     gwfcore_iam_template = included_gwfcore_iam_stack.included_template
    #     gwfcore_batch_instance_role = gwfcore_iam_template.get_resource("BatchInstanceRole")
    #     assert isinstance(gwfcore_batch_instance_role, cdk_iam.CfnRole)
    #     gwfcore_batch_instance_role.managed_policy_arns.append(
    #         cdk_iam.ManagedPolicy.from_aws_managed_policy_name(
    #             "AmazonElasticFileSystemClientReadWriteAccess"
    #         ).managed_policy_arn
    #     )

    #     # Set a tag on the batch queue to help miniwdl-aws identify it as the default
    #     # !!!!!!!!!!!!!!!!! maybe just do this manually idk
    #     # gwfcore_batch_template = cfn_gwfcore.get_nested_stack("BatchStack").included_template
    #     # cdk.Tags.of(gwfcore_batch_template.get_resource("DefaultQueue")).add(
    #     #     "MiniwdlStudioFsxId", studio_fsx_id
    #     # )

    #     batch_sg = cdk_ec2.SecurityGroup.from_security_group_id(
    #         self,
    #         "BatchSecurityGroup",
    #         gwfcore_batch_template.get_resource("SecurityGroup").attr_group_id,
    #     )
    #     return batch_sg
