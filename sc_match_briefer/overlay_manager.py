OPEN_OVERLAYS = []


def register_overlay(widget):
    OPEN_OVERLAYS.append(widget)


def close_all_overlays():
    for w in OPEN_OVERLAYS:
        try:
            w.close()
        except:
            pass
    OPEN_OVERLAYS.clear()
