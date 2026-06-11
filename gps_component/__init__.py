"""gps_component — HTML5 Geolocation custom Streamlit component.

Mobil tarayıcıda 'Konumumu Al' butonu → navigator.geolocation.getCurrentPosition()
→ lat/lon Streamlit session'a döner.

Kullanım:
    from gps_component import gps_button
    coords = gps_button(label="📍 Konumumu Al")
    if coords:
        lat, lon = coords
"""
import os
import streamlit as st
import streamlit.components.v1 as components

# Component dosyalarının yolu
_COMPONENT_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.join(_COMPONENT_DIR, "frontend")


# Component'i declare et (build gerekmez — saf HTML/JS)
_gps_component = components.declare_component(
    "gps_button",
    path=_FRONTEND_DIR,
)


def gps_button(
    label: str = "📍 Konumumu Al",
    key: str = None,
    default_lat: float = None,
    default_lon: float = None,
    high_accuracy: bool = True,
) -> tuple[float, float] | None:
    """Konum al butonu. Tıklanınca tarayıcı konum ister.

    Returns:
        (lat, lon) tuple veya None (henüz tıklanmamışsa / hata varsa)
    """
    coords = _gps_component(
        label=label,
        defaultLat=default_lat,
        defaultLon=default_lon,
        highAccuracy=high_accuracy,
        key=key,
    )
    if coords and isinstance(coords, dict) and "lat" in coords and "lon" in coords:
        return (float(coords["lat"]), float(coords["lon"]))
    return None
