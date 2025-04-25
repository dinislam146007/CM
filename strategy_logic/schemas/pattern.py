from enum import Enum


class Pattern(Enum):
    PIN_BAR_LONG = "PinBar 🟢"
    INSIDE_BAR_LONG = "InsideBar 🟢"
    FAKEY_LONG = "Fakey 🟢"
    OUTSIDE_BAR_LONG = "OutsideBar 🟢"
    PPR_LONG = "PPR 🟢"

    PIN_BAR_SHORT = "PinBar 🔴"
    INSIDE_BAR_SHORT = "InsideBar 🔴"
    FAKEY_SHORT = "Fakey 🔴"
    OUTSIDE_BAR_SHORT = "OutsideBar 🔴"
    PPR_SHORT = "PPR 🔴"
