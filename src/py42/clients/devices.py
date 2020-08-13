import json
from copy import deepcopy

from py42 import settings
from py42._internal.compat import ChainMap
from py42.clients import BaseClient
from py42.clients.util import get_all_pages
from py42.exceptions import Py42Error


class DeviceConfig(object):
    def __init__(self, config_json):
        pass


class BackupSet(object):
    def __init__(self, settings_manager, set_dict):
        self._manager = settings_manager
        backup_paths_dict = set_dict.pop("backupPaths")
        self._set = ChainMap({}, set_dict)
        self._backup_paths = ChainMap({}, backup_paths_dict)

    @property
    def backup_paths(self):
        pathset = self._backup_paths["pathset"][0]["path"]
        return [p["@include"] for p in pathset if "@include" in p]

    def add_backup_path(self, path):
        pathset = deepcopy(self._backup_paths["pathset"])
        pathset[0]["path"].append({"@include": path})
        self._backup_paths["pathset"] = pathset

    @property
    def backup_path_excludes(self):
        pathset = self._backup_paths["pathset"][0]["path"]
        return [p["@exclude"] for p in pathset if "@exclude" in p]

    def exclude_backup_path(self, path):
        pathset = deepcopy(self._backup_paths["pathset"])
        path_list = pathset[0]["path"]
        path_list.append({"@exclude": path})
        if {"@include": path} in path_list:
            path_list.remove({"@include": path})
        pathset[0]["path"] = path_list
        self._backup_paths["pathset"] = pathset

    @property
    def filename_exclusions(self):
        excludes = self._set["backupPaths"]["excludeUser"][0].get("pattern")
        if excludes:
            return [e["@regex"] for e in excludes]
        return []

    def add_filename_exclusion(self, regex_string):
        user_excludes = deepcopy(self._set["backupPaths"]["excludeUser"])

    def add_destination(self, destination_guid):
        if destination_guid in self._manager.available_destinations:
            if destination_guid not in list(self._set["destinations"].values()):
                self._set["destinations"].append({"@id": destination_guid})
        else:
            raise Py42Error(
                "Invalid destination guid or destination not offered to device's Org."
            )


class DeviceSettingsManager(object):
    def __init__(self, device_client, guid):
        device_response = device_client.get_by_guid(guid, incSettings=True)
        uri = u"/api/DeviceSetting/{}".format(guid)
        device_settings_response = device_client._session.get(uri)

        device_dict = device_response.data
        settings_dict = device_dict.pop("settings")
        service_config_dict = settings_dict.pop("serviceBackupConfig")
        backup_config_dict = service_config_dict.pop("backupConfig")

        self.available_destinations = {
            d["guid"]: d["destinationName"]
            for d in device_dict["availableDestinations"]
        }
        self._device = ChainMap({}, device_dict)
        self._settings = ChainMap({}, settings_dict)
        self._service_config = ChainMap({}, service_config_dict)
        self._backup_config = ChainMap({}, backup_config_dict)
        self._device_settings = ChainMap({}, device_settings_response.data)
        self._device_client = device_client
        self._errored = None
        self.backup_sets = [
            BackupSet(self, set_dict) for set_dict in self._backup_config["backupSets"]
        ]
        self.settings_response = None
        self.device_settings_response = None

    @property
    def name(self):
        return self._device["name"]

    @name.setter
    def name(self, value):
        self._device["name"] = value

    @property
    def external_reference(self):
        return self._device["computerExtRef"]

    @external_reference.setter
    def external_reference(self, value):
        self._device["computerExtRef"] = value

    @property
    def notes(self):
        return self._device["notes"]

    @notes.setter
    def notes(self, value):
        self._device["notes"] = value

    def update(self):
        updates, original = self._device.maps
        payload = original
        payload.update(updates)
        self._device_client.put_to_computer_endpoint(
            self._device["computerId"], payload
        )


class DeviceClient(BaseClient):
    """A class to interact with Code42 device/computer APIs."""

    def get_page(
        self,
        page_num,
        active=None,
        blocked=None,
        org_uid=None,
        user_uid=None,
        destination_guid=None,
        include_backup_usage=None,
        include_counts=True,
        page_size=None,
        q=None,
    ):
        """Gets a page of devices.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#Computer-get>`__

        Args:
            page_num (int): The page number to request.
            active (bool, optional): Filters results by device state. When set to True, gets all
                active devices. When set to False, gets all deactivated devices. When set to None
                or excluded, gets all devices regardless of state. Defaults to None.
            blocked (bool, optional): Filters results by blocked status: True or False. Defaults
                to None.
            org_uid (int, optional): The identification number of an Organization. Defaults to None.
            user_uid (int, optional): The identification number of a User. Defaults to None.
            destination_guid (str or int, optional): The globally unique identifier of the storage
                server that the device back up to. Defaults to None.
            include_backup_usage (bool, optional): A flag to denote whether to include the
                destination and its backup stats. Defaults to None.
            include_counts (bool, optional): A flag to denote whether to include total, warning,
                and critical counts. Defaults to True.
            page_size (int, optional): The number of devices to return per page. Defaults to
                `py42.settings.items_per_page`.
            q (str, optional): Searches results flexibly by incomplete GUID, hostname,
                computer name, etc. Defaults to None.

        Returns:
            :class:`py42.response.Py42Response`
        """

        uri = u"/api/Computer"
        page_size = page_size or settings.items_per_page
        params = {
            u"active": active,
            u"blocked": blocked,
            u"orgUid": org_uid,
            u"userUid": user_uid,
            u"targetComputerGuid": destination_guid,
            u"incBackupUsage": include_backup_usage,
            u"incCounts": include_counts,
            u"pgNum": page_num,
            u"pgSize": page_size,
            u"q": q,
        }

        return self._session.get(uri, params=params)

    def get_all(
        self,
        active=None,
        blocked=None,
        org_uid=None,
        user_uid=None,
        destination_guid=None,
        include_backup_usage=None,
        include_counts=True,
        q=None,
        **kwargs
    ):
        """Gets all device information.

        When no arguments are passed, all records are returned. To filter results, specify
        respective arguments. For example, to retrieve all active and blocked devices, pass
        active=true and blocked=true.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#Computer-get>`__

        Args:
            active (bool, optional): Filters results by device state. When set to True, gets all
                active devices. When set to False, gets all deactivated devices. When set to None
                or excluded, gets all devices regardless of state. Defaults to None.
            blocked (bool, optional): Filters results by blocked status: True or False. Defaults
                to None.
            org_uid (int, optional): The identification number of an Organization. Defaults to None.
            user_uid (int, optional): The identification number of a User. Defaults to None.
            destination_guid (str or int, optional): The globally unique identifier of the storage
                server that the device back up to. Defaults to None.
            include_backup_usage (bool, optional): A flag to denote whether to include the
                destination and its backup stats. Defaults to None.
            include_counts (bool, optional): A flag to denote whether to include total, warning,
                and critical counts. Defaults to True.
            q (str, optional): Searches results flexibly by incomplete GUID, hostname,
                computer name, etc. Defaults to None.

        Returns:
            generator: An object that iterates over :class:`py42.response.Py42Response` objects
            that each contain a page of devices.

            The devices returned by `get_all()` are based on the role and permissions of the user
            authenticating the py42 SDK.
        """

        return get_all_pages(
            self.get_page,
            u"computers",
            active=active,
            blocked=blocked,
            org_uid=org_uid,
            user_uid=user_uid,
            destination_guid=destination_guid,
            include_backup_usage=include_backup_usage,
            include_counts=include_counts,
            q=q,
            **kwargs
        )

    def get_by_id(self, device_id, include_backup_usage=None, **kwargs):
        """Gets device information by ID.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#Computer-get>`__

        Args:
            device_id (int): The identification number of the device.
            include_backup_usage (bool, optional): A flag to denote whether to include the
                destination and its backup stats. Defaults to None.

        Returns:
            :class:`py42.response.Py42Response`: A response containing device information.
        """
        uri = u"/api/Computer/{}".format(device_id)
        params = dict(incBackupUsage=include_backup_usage, **kwargs)
        return self._session.get(uri, params=params)

    def get_by_guid(self, guid, include_backup_usage=None, **kwargs):
        """Gets device information by GUID.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#Computer-get>`__

        Args:
            guid (str): The globally unique identifier of the device.
            include_backup_usage (bool, optional): A flag to denote whether to include the
                destination and its backup stats. Defaults to None.

        Returns:
            :class:`py42.response.Py42Response`: A response containing device information.
        """
        uri = u"/api/Computer/{}".format(guid)
        params = dict(idType=u"guid", incBackupUsage=include_backup_usage, **kwargs)
        return self._session.get(uri, params=params)

    def block(self, device_id):
        """Blocks a device causing the user not to be able to log in to or restore from Code42 on
        that device.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#ComputerBlock>`__

        Args:
            device_id (int): The identification number of the device.

        Returns:
            :class:`py42.response.Py42Response`
        """
        uri = u"/api/ComputerBlock/{}".format(device_id)
        return self._session.put(uri)

    def unblock(self, device_id):
        """Unblocks a device, permitting a user to be able to login and restore again.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#ComputerBlock>`__

        Args:
            device_id (int): The identification number of the device.

        Returns:
            :class:`py42.response.Py42Response`
        """
        uri = u"/api/ComputerBlock/{}".format(device_id)
        return self._session.delete(uri)

    def deactivate(self, device_id):
        """Deactivates a device, causing backups to stop and archives to go to cold storage.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#ComputerDeactivation>`__

        Args:
            device_id (int): The identification number of the device.

        Returns:
            :class:`py42.response.Py42Response`
        """
        uri = u"/api/v4/computer-deactivation/update"
        data = {u"id": device_id}
        return self._session.post(uri, data=json.dumps(data))

    def reactivate(self, device_id):
        """Activates a previously deactivated device.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#ComputerDeactivation>`__

        Args:
            device_id (int): The identification number of the device.

        Returns:
            :class:`py42.response.Py42Response`
        """
        uri = u"/api/v4/computer-deactivation/remove"
        data = {u"id": device_id}
        return self._session.post(uri, data=json.dumps(data))

    def deauthorize(self, device_id):
        """Deauthorizes the device with the given ID. If used on a cloud connector device, it will
        remove the authorization token for that account.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#ComputerDeauthorization>`__

        Args:
            device_id (int): The identification number of the device.

        Returns:
            :class:`py42.response.Py42Response`
        """
        uri = u"/api/ComputerDeauthorization/{}".format(device_id)
        return self._session.put(uri)

    def get_settings(self, guid, keys=None):
        """Gets settings of the device.
        `REST Documentation <https://console.us.code42.com/apidocviewer/#DeviceSetting>`__

        Args:
            guid (str): The globally unique identifier of the device.
            keys (str, optional): A comma separated list of device keys. Defaults to None.

        Returns:
            :class:`py42.response.Py42Response`: A response containing settings information.
        """
        uri = u"/api/v4/device-setting/view"
        params = {u"guid": guid, u"keys": keys}
        return self._session.get(uri, params=params)

    def put_to_computer_endpoint(self, device_id, data):
        uri = "/api/Computer/{}".format(device_id)
        self._session.put(uri, data=json.dumps(data))

    def get_agent_state(self, guid, property_name):
        """Gets the agent state of the device.
            `REST Documentation <https://console.us.code42.com/swagger/index.html?urls.primaryName=v14#/agent-state/AgentState_ViewByDeviceGuid>`__

            Args:
                guid (str): The globally unique identifier of the device.
                property_name (str): The name of the property to retrieve (e.g. `fullDiskAccess`).

            Returns:
                :class:`py42.response.Py42Response`: A response containing settings information.
            """
        uri = u"/api/v14/agent-state/view-by-device-guid"
        params = {u"deviceGuid": guid, u"propertyName": property_name}
        return self._session.get(uri, params=params)

    def get_agent_full_disk_access_state(self, guid):
        """Gets the full disk access status of a device.
            `REST Documentation <https://console.us.code42.com/swagger/index.html?urls.primaryName=v14#/agent-state/AgentState_ViewByDeviceGuid>`__

            Args:
                guid (str): The globally unique identifier of the device.

            Returns:
                :class:`py42.response.Py42Response`: A response containing settings information.
            """
        return self.get_agent_state(guid, u"fullDiskAccess")
