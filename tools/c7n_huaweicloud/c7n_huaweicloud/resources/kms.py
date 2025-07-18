# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import logging
import uuid
import time

from huaweicloudsdkkms.v2 import (EnableKeyRotationRequest, OperateKeyRequestBody,
                                  DisableKeyRotationRequest, EnableKeyRequest,
                                  DisableKeyRequest, CreateKeyRequest, CreateKeyRequestBody,
                                  ListAliasesRequest, CreateAliasRequest,
                                  CreateAliasRequestBody, ListKeysRequest, ListKmsByTagsRequest,
                                  ListKmsByTagsRequestBody)

from c7n import exceptions
from c7n.filters import ValueFilter
from c7n.utils import type_schema, local_session
from c7n_huaweicloud.actions.base import HuaweiCloudBaseAction
from c7n_huaweicloud.provider import resources
from c7n_huaweicloud.query import QueryResourceManager, TypeInfo

log = logging.getLogger("custodian.huaweicloud.resources.kms")


@resources.register('kms')
class Kms(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'kms'
        enum_spec = ("list_keys", 'key_details', 'offset')
        id = 'key_id'
        tag_resource_type = 'kms'
        config_resource_support = True

    def get_resources(self, resource_ids):
        allResources = self.get_api_resources(resource_ids)
        resources = []
        for resource in allResources:
            if resource["key_id"] in resource_ids:
                resources.append(resource)
        return resources

    def _fetch_resources(self, query):
        return self.get_api_resources(query)

    def get_api_resources(self, resource_ids):
        session = local_session(self.session_factory)
        client = session.client(self.resource_type.service)
        resources = []
        resourceTagDict = {}
        offset, limit = 0, 1000
        while True:

            requestTag = ListKmsByTagsRequest()
            requestTag.resource_instances = "resource_instances"
            requestTag.body = ListKmsByTagsRequestBody(
                action="filter",
                offset=str(offset),
                limit=str(limit)
            )

            try:
                responseTag = client.list_kms_by_tags(requestTag)
                tagResources = responseTag.resources
                for tagResource in tagResources:
                    resourceTagDict[tagResource.resource_id] = tagResource.to_dict().get('tags')

            except Exception as e:
                log.error(
                    f"Failed to query API list: {str(e)}")
                break

            offset += limit

            if not responseTag.total_count or offset >= len(responseTag.resources):
                break

        request = ListKeysRequest()
        request.key_spec = "ALL"
        try:
            response = client.list_keys(request)
            details = response.key_details
            default = []
            for detail in details:
                dict = detail.to_dict()
                dict["tags"] = resourceTagDict.get(detail.key_id, default)
                dict["id"] = detail.key_id
                resources.append(dict)
        except Exception as e:
            log.error(
                f"Failed to query API list: {str(e)}")
            raise e
        return resources


@Kms.action_registry.register("enable_key_rotation")
class rotationKey(HuaweiCloudBaseAction):
    """rotation kms key.

    :Example:

    .. code-block:: yaml

policies:
  - name: enable_key_rotation
    resource: huaweicloud.kms
    filters:
        - type: value
          key: key_rotation_enabled
          value: "False"
        - type: value
          key: domain_id
          value: "537f650fb2be4ca3a511f25d8defd3b0"
        - type: value
          key: default_key_flag
          value: "0"
        - type: value
          key: keystore_id
          value: "0"
        - type: value
          key: key_state
          value: "2"
    actions:
      - enable_key_rotation
    """

    schema = type_schema("enable_key_rotation")

    def perform_action(self, resource):
        supportList = {"AES_256", "SM4"}
        resourceId = resource["key_id"]
        if (resource["default_key_flag"] == "0" and resource["key_spec"]
                in supportList and resource["keystore_id"] == "0"
                and resource["key_state"] in {"2"}):
            client = self.manager.get_client()
            request = EnableKeyRotationRequest()
            request.body = OperateKeyRequestBody(
                key_id=resource["key_id"],
                sequence=uuid.uuid4().hex
            )
            try:
                client.enable_key_rotation(request)
                log.info("enable_key_rotation the resourceType:KMS resourceId={},success"
                         .format(resourceId))
            except Exception as e:
                if e.status_code == 400:
                    log.info(
                        "the key rotation is already enabled or the key is not supported "
                        "for rotation, resourceId={},msg={}".format(
                            resourceId, e.error_msg))
                else:
                    log.error("enable_key_rotation the resourceType:KMS resourceId={} is failed"
                              .format(resourceId))

        else:
            log.info("skip enable_key_rotation the resourceType:KMS resourceId={},"
                     "The key does not meet the conditions for "
                     "enabling rotation.The conditions for ending the key are:"
                     "the key is not the default key,is not a shared "
                     "key,and the algorithm is SM4 or AES_256".format(resourceId))


@Kms.action_registry.register("disable_key_rotation")
class disableRotationKey(HuaweiCloudBaseAction):
    """rotation kms key.

    :Example:

    .. code-block:: yaml

policies:
  - name: enable_key_rotation
    resource: huaweicloud.kms
    filters:
        - type: value
          key: key_rotation_enabled
          value: "False"
        - type: value
          key: domain_id
          value: "537f650fb2be4ca3a511f25d8defd3b0"
    actions:
      - disable_key_rotation
    """

    schema = type_schema("disable_key_rotation")

    def perform_action(self, resource):
        notSupportList = {"RSA_2048", "RSA_3072", "RSA_4096", "EC_P256", "EC_P384",
                          "SM2", "ML_DSA_44", "ML_DSA_65", "ML_DSA_87"}

        if (resource["default_key_flag"] == "0" and resource["key_spec"]
                not in notSupportList and resource["keystore_id"] == "0"
                and resource["key_state"] in {"2", "3", "4"}):
            client = self.manager.get_client()
            request = DisableKeyRotationRequest()
            request.body = OperateKeyRequestBody(
                key_id=resource["key_id"],
                sequence=uuid.uuid4().hex
            )
            try:
                client.disable_key_rotation(request)
            except Exception as e:
                raise e


@Kms.action_registry.register("enable_key")
class enableKey(HuaweiCloudBaseAction):
    """rotation kms key.

    :Example:

    .. code-block:: yaml

    policies:
      - name: enable_key
        resource: huaweicloud.kms
        filters:
          - type: value
            key: key_state
            value: "3"
        actions:
          - enable_key
    """

    schema = type_schema("enable_key")

    def perform_action(self, resource):
        client = self.manager.get_client()

        request = EnableKeyRequest()
        request.body = OperateKeyRequestBody(
            key_id=resource["key_id"],
            sequence=uuid.uuid4().hex
        )
        try:
            response = client.enable_key(request)
        except Exception as e:
            raise e

        return response


@Kms.action_registry.register("disable_key")
class disableKey(HuaweiCloudBaseAction):
    """rotation kms key.

    :Example:

    .. code-block:: yaml

    policies:
      - name: disable_key
        resource: huaweicloud.kms
        filters:
          - type: value
            key: key_state
            value: "2"
        actions:
          - disable_key
    """

    schema = type_schema("disable_key")

    def perform_action(self, resource):
        client = self.manager.get_client()
        request = DisableKeyRequest()
        request.body = OperateKeyRequestBody(
            key_id=resource["key_id"],
            sequence=uuid.uuid4().hex
        )
        try:
            response = client.disable_key(request)
        except Exception as e:
            raise e

        return response


@Kms.action_registry.register("create-key-with-alias")
class createKey(HuaweiCloudBaseAction):
    """rotation kms key.

    :Example:

    .. code-block:: yaml

policies:
  - name: create-key-with-alias
    resource: huaweicloud.kms
    mode:
      type: huaweicloud-periodic
      xrole: fgs_admin
      enable_lts_log: true
      log_level: INFO
      schedule: '1m'
      schedule_type: Rate
    actions:
      - type: create-key-with-alias
        key_aliases: ["test"]
        obs_url: "https://custodian0527.obs.sa-brazil-1.myhuaweicloud.com/kms.txt"

    """

    schema = type_schema("create-key-with-alias",
                         key_aliases={"type": "array"},
                         obs_url={"type": "string"})

    def process(self, resource):

        client = self.manager.get_client()
        all_key_aliases = set()
        key_aliases = self.data.get("key_aliases", [])
        all_key_aliases.update(key_aliases)
        obs_url = self.data.get("obs_url", None)
        obs_client = local_session(self.manager.session_factory).client("obs")
        if not key_aliases and obs_url is None:
            log.error("key_aliases or obs_url is required")
            return []
        if obs_url is not None and obs_url != '':
            # 1. 提取第一个变量：从 "https://" 到最后一个 "obs" 的部分
            protocol_end = len("https://")
            # 去除协议头后的完整路径
            path_without_protocol = obs_url[protocol_end:]
            obs_bucket_name = self.get_obs_name(path_without_protocol)
            obs_server = self.get_obs_server(path_without_protocol)
            obs_file = self.get_file_path(path_without_protocol)
            obs_client.server = obs_server
            try:
                resp = obs_client.getObject(bucketName=obs_bucket_name,
                                            objectKey=obs_file,
                                            loadStreamInMemory=True)
                if resp.status < 300:
                    all_key_aliases.update(json.loads(resp.body.buffer)['obs_key_aliases'])
                else:
                    log.error(f"get obs object failed: {resp.errorCode}, {resp.errorMessage}")
                    return []
            except exceptions.ClientRequestException as e:
                log.error(e.status_code, e.request_id, e.error_code, e.error_msg)
                raise

        listAliasesRequest = ListAliasesRequest()
        listAliasResponse = client.list_aliases(listAliasesRequest)
        arr = set()
        for realAlias in listAliasResponse.body[0].aliases:
            arr.add(realAlias.alias.replace('alias/', ''))

        if len(all_key_aliases) != 0:
            for alias in all_key_aliases:
                if alias not in arr:
                    timestamp = int(time.time())
                    keyName = str(timestamp)
                    createKeyRequest = CreateKeyRequest()
                    createKeyRequest.body = CreateKeyRequestBody(
                        key_alias=keyName
                    )
                    try:
                        createKeyResponse = client.create_key(createKeyRequest)
                        createKeyId = createKeyResponse.key_info.key_id
                        createAliasRequest = CreateAliasRequest()
                        createAliasRequest.body = CreateAliasRequestBody(
                            key_id=createKeyId,
                            alias="alias/" + alias
                        )
                        client.create_alias(createAliasRequest)
                        time.sleep(1)
                    except Exception as e:
                        raise e

    def perform_action(self, resource):
        return super().perform_action(resource)

    def get_obs_name(self, obs_url):
        # 找到最后一个 ".obs" 的索引位置
        last_obs_index = obs_url.rfind(".obs")
        return obs_url[:last_obs_index]

    def get_obs_server(self, obs_url):
        # 找到最后一个 ".obs" 的索引位置
        last_obs_index = obs_url.rfind(".obs")
        remaining_after_obs = obs_url[last_obs_index:]
        split_res = remaining_after_obs.split("/", 1)
        return split_res[0].lstrip(".")

    def get_file_path(self, obs_url):
        # 找到最后一个 ".obs" 的索引位置
        last_obs_index = obs_url.rfind(".obs")
        remaining_after_obs = obs_url[last_obs_index:]
        split_res = remaining_after_obs.split("/", 1)
        return split_res[1]


@Kms.filter_registry.register("all_keys_disable")
class instanceDisable(ValueFilter):
    '''
    policies:
      - name: all_keys_disable
        resource: huaweicloud.kms
        filters:
          - type: all_keys_disable
            key: "key_state"
            value: "2"
    '''
    schema = type_schema("all_keys_disable",
                         rinherit=ValueFilter.schema)
