from py42._compat import string_type
from py42.clients.settings.converters import bool_to_str
from py42.clients.settings.converters import no_conversion
from py42.clients.settings.converters import str_to_bool


def set_val(d, keys, value):
    """Helper for setting nested values from a dict based on a list of keys."""
    d = get_val(d, keys[:-1])
    d[keys[-1]] = value


def get_val(d, keys):
    """Helper for getting nested values from a dict based on a list of keys."""
    for key in keys:
        d = d[key]
    return d


def show_change(val1, val2):
    if isinstance(val1, string_type):
        val1 = '"{}"'.format(val1)
    if isinstance(val2, string_type):
        val2 = '"{}"'.format(val2)
    return "{} -> {}".format(val1, val2)


class BaseSettingProperty(object):
    def __init__(self, name, location):
        self.name = name
        self.location = location
        self.init_val = None

    def _register_change(self, instance, orig_val, new_val):
        name = self.name.lstrip("_")
        if self.init_val is None:
            self.init_val = orig_val
        if self.init_val == new_val:
            if name in instance.changes:
                instance.changes.pop(name)
        else:
            instance.changes[name] = show_change(self.init_val, new_val)


class SettingProperty(BaseSettingProperty):
    """Descriptor class to help manage changes to nested dict values. Assumes attributes
    being managed are on a UserDict/UserList subclass.

    Args:
        name (str): name of attribute this class manages (changes will be registered with this name).
        location (list): list of keys defining the location of the value being managed in the managed class.
        get_converter (func, optional): function to convert retrieved values to preferred format. Defaults to no conversion.
        set_converter (func, optional): function to convert values being set to preferred format. Defaults to no conversion.
    """

    def __init__(
        self, name, location, get_converter=no_conversion, set_converter=no_conversion
    ):
        super(SettingProperty, self).__init__(name, location)
        self.get_converter = get_converter
        self.set_converter = set_converter

    def __get__(self, instance, owner):
        val = get_val(instance.data, self.location)
        if isinstance(val, dict):
            val = val["#text"]
        return self.get_converter(val)

    def __set__(self, instance, new_val):
        converted_new_val = self.set_converter(new_val)
        orig_val = get_val(instance.data, self.location)

        # if locked, value is a dict with '#text' as the _real_ value key
        if isinstance(orig_val, dict):
            location = self.location + ["#text"]
            orig_val = orig_val["#text"]
        else:
            location = self.location

        self._register_change(instance, orig_val, converted_new_val)
        set_val(instance.data, location, converted_new_val)


class SettingLockProperty(BaseSettingProperty):
    """Descriptor class to help manage changes to the locked status of nested dict values. Assumes attributes
        being managed are on a UserDict/UserList subclass.

        Args:
            name (str): name of attribute this class manages (changes will be registered with this name).
            location (list): list of keys defining the location of the value being managed in the managed class.
        """

    def __get__(self, instance, owner):
        val = get_val(instance.data, self.location)
        if isinstance(val, dict):
            return str_to_bool(val["@locked"])
        else:
            return False

    def __set__(self, instance, new_val):
        val_string = bool_to_str(new_val)
        currently_locked = getattr(instance, self.name)
        if currently_locked and new_val:
            return
        elif not currently_locked and not new_val:
            return
        else:
            current_setting_value = get_val(instance.data, self.location)
            if isinstance(current_setting_value, dict):
                current_locked_value = str_to_bool(current_setting_value["@locked"])
                current_setting_value = current_setting_value["#text"]
            else:
                current_locked_value = False
            self._register_change(instance, current_locked_value, new_val)
            set_val(
                instance.data,
                self.location,
                {
                    "#text": current_setting_value,
                    "@locked": val_string,
                    "@publish": "true",
                },
            )


class TSettingProperty(object):
    """Descriptor class to help manage transforming t_setting packet values. Assumes t_setting
    dict is stored in `._t_settings` attribute on managed instances.

    Args:
        name (str): name of attribute this class manages (changes will be registered with this name).
        key (str): name of t_setting packet this class is managing.
    """

    def __init__(self, name, key, enforce_bool=False):
        self.name = name
        self.key = key
        self.enforce_bool = enforce_bool
        self.init_val = None

    def __get__(self, instance, owner):
        packet = instance._t_settings[self.key]
        return str_to_bool(packet["value"])

    def __set__(self, instance, val):
        if self.enforce_bool:
            val = bool_to_str(val)
        packet = {"key": self.key, "value": val, "locked": False}
        instance._packets[self.key] = packet
        self._register_change(instance, val)

    def _register_change(self, instance, val):
        if self.init_val is None:
            self.init_val = instance._t_settings[self.key]["value"]
        if self.init_val == val:
            if self.name in instance.changes:
                instance.changes.pop(self.name)
        else:
            instance.changes[self.name] = show_change(self.init_val, val)


class TSettingLockProperty(object):
    def __init__(self, name, key):
        self.name = name
        self.key = key
        self.init_val = None

    def __get__(self, instance, owner):
        packet = instance._t_settings[self.key]
        return str_to_bool(packet["@locked"])

    def __set__(self, instance, new_val):
        new_val_string = bool_to_str(new_val)
        packet = instance._t_settings[self.key]
        if self.init_val is None:
            self.init_val = str_to_bool(packet["@locked"])
        packet = {"key"}

        name = self.name.lstrip("_")
        try:
            changes = instance.changes
        except AttributeError:
            changes = instance._changes
        if self.init_val == new_val:
            if name in changes:
                changes.pop(name)
        else:
            changes[name] = new_val_string
