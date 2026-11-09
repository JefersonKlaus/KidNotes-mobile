"""Design tokens (colors) used across the app."""

COLORS = {
    "background": "#FFF9F4",
    "surface": "#FFFFFF",
    "ink": "#354052",
    "muted": "#788396",
    "primary": "#6C8CE5",
    "lavender": "#EEEAFE",
    "mint": "#E7F5EE",
    "peach": "#FFF0E1",
    "border": "#E8E8EF",
    # Disabled controls (e.g. "Take photo" where there is no camera).
    "disabled": "#E4E6EB",
    "disabled_text": "#9AA1AD",
    # Transferred (deactivated) students on the class screen.
    "inactive_surface": "#F3F4F6",
}

# Colors a teacher can pick for a class (the first one is the default).
CLASS_COLORS = [
    "#F8C8D8",
    "#B8DCEB",
    "#B8E0C8",
    "#F6D6A8",
    "#C9B8E8",
    "#A8D8EA",
]

# Avatar colors for students (picked from the student id, so they are stable).
AVATAR_COLORS = [
    "#F4A7C1",
    "#A8D8EA",
    "#B8E0C8",
    "#F6D6A8",
    "#C9B8E8",
]
