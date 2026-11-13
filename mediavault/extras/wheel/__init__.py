"""Wheel of fortune: spin a wheel over free-text entries or library groups.

The whole interface to the app is :class:`WheelPage`: it takes the theme
palette and a callable returning the library's group names, and follows theme
changes through :meth:`WheelPage.apply_theme`. It never sees media entries.

- :mod:`.page`: the wheel widget and the page around it.
- :mod:`.group_dialog`: choose which library groups go on the wheel.
- :mod:`.configs`: saved entry lists in ``~/.mediavault/wheel_configs.json``.
"""

from mediavault.extras.wheel.page import WheelPage

__all__ = ["WheelPage"]
