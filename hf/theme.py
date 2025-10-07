LIONS_COLORS = {
    "honolulu_blue": "#0076B6",
    "silver": "#B0B7BC",
    "deep_navy": "#0A0F14",
    "dark_slate": "#101820",
    "white": "#F0F3F5",
}

def kpi_style() -> str:
    return (
        """
        <style>
        .kpi-card {background: #101820; border: 1px solid #1f2a34; border-radius: 12px; padding: 16px;}
        .kpi-value {font-size: 32px; font-weight: 700; color: #F0F3F5;}
        .kpi-label {font-size: 13px; color: #B0B7BC; text-transform: uppercase; letter-spacing: .06em;}
        </style>
        """
    )

