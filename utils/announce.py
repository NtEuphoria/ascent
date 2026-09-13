"""The Studios introduction card.

Shown once, under the section switcher, pointing at the Studios button. It
exists because a new section that simply appears in a switcher is a section
nobody clicks: the icon says where it is and nothing says what it is for.

Modelled on the way a new capability gets introduced rather than on a tooltip -
an image, a name, two sentences of what it actually does, and one way in. It
is dismissible and never returns, because an announcement that reappears is an
advertisement.

The hero is drawn here as SVG so the app carries no binary asset and still
works offline. Dropping a PNG at assets/studios-hero.png overrides it, which
is how a real photograph gets in without changing any code.
"""
from __future__ import annotations

import os
from typing import Optional

import streamlit as st

from . import settings as user_settings

HERO_PNG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "studios-hero.png")

TITLE = "Introducing Studios"
BODY = ("A calculator answers one question. A studio carries a whole design "
        "through - what the job demands, whether the hardware can deliver it, "
        "and whether the thing holding it together survives - and ends in a "
        "verdict rather than a number.")


def hero_path() -> Optional[str]:
    """The image to show above the text, or None if none was supplied.

    An eighty-kilobyte data URI was tried first, both as an <img> inside the
    card's markup and as a CSS background. st.markdown strips <img> and <svg>
    outright, and a base64 url() inside the stylesheet took the ENTIRE
    stylesheet down with it - the app rendered in Streamlit's default colours
    with no tokens defined at all. st.image is the supported route and simply
    works, at the cost of the picture being its own element rather than part
    of the card's markup.
    """
    return HERO_PNG if os.path.isfile(HERO_PNG) else None


def needed(prefs: dict) -> bool:
    return not prefs.get("studios_announced", False)


def dismiss() -> None:
    user_settings.update(studios_announced=True)


def card(prefs: dict, on_open) -> None:
    """Draw the card. `on_open` is called if the user chooses to go there.

    Rendered in the sidebar right under the switcher, with an arrow aimed at
    the Studios button, because an announcement that is not attached to the
    thing it announces is just a notice.
    """
    if not needed(prefs):
        return

    with st.container(key="announce"):
        picture = hero_path()
        if picture:
            # width="stretch", not use_container_width: the latter is
            # deprecated in Streamlit 1.50, is ignored, and left the picture
            # rendering 15 pixels wide.
            st.image(picture, width="stretch")
        # The supplied artwork carries the name already, so repeating it in
        # text underneath says the same thing twice. Without artwork the card
        # needs a headline of its own.
        heading = "" if picture else f'<div class="a-ann-title">{TITLE}</div>'
        st.markdown(
            f'<div class="a-ann"><div class="a-ann-body">{heading}'
            f'<p>{BODY}</p></div></div>',
            unsafe_allow_html=True)
        open_column, dismiss_column = st.columns([1.35, 1])
        with open_column:
            if st.button("Open Studios", key="ann_open", type="primary",
                         use_container_width=True):
                dismiss()
                on_open()
        with dismiss_column:
            if st.button("Not now", key="ann_dismiss",
                         use_container_width=True):
                dismiss()
                st.rerun()
