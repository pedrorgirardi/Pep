import sublime_plugin
import sublime


# History by window ID.
jump_history = {}

# Zero based jump position by window ID.
jump_pos = {}


def _window_history(window):
    global jump_history

    if window.id() in jump_history:
        return jump_history[window.id()]
    else:
        history = []

        jump_history[window.id()] = history

        return history


def _jump_pos_for_window(window):
    global jump_pos
    
    if window.id() in jump_pos:
        return jump_pos[window.id()]

    history = _window_history(window)

    if history:
        pos = len(history) - 1

        jump_pos[window.id()] = pos

        return pos
    else:
        # There is no history. We can't jump.
        return None


class PepJumpListener(sublime_plugin.EventListener):
    """
    Many things were copied from Default/history_list.py
    """

    def _valid_view(self, view):
        """
        Determines if we want to track the history for a view

        :param view:
            A sublime.View object

        :return:
            A bool if we should track the view
        """

        return view is not None and not view.settings().get('is_widget')


    def on_modified(self, view):
        if not self._valid_view(view):
            return

        # Only the last selection is relevant to our jump history.
        region = view.sel()[-1]

        history = _window_history(view.window())

        history.append({"view": view,
                        "region": region})

        print(">", region)

        # Remove first n elements whenever history grows above threshold.
        if len(history) > 50:
            del history[:10]

class PgJumpBackChangeCommand(sublime_plugin.TextCommand):

    def is_enabled(self):
        return not self.view.settings().get('is_widget')


    def run(self, edit):

        global jump_pos

        window = self.view.window()  

        history = _window_history(window)

        if history:
            pos = _jump_pos_for_window(window)
            
            # Can't jump if there isn't a jump position,
            # or if there is a single entry in the history.
            if pos is None or pos == 0: 
                return

            # Actual jump position is last pos - 1.
            _pos = pos - 1

            history_entry = history[_pos]

            view = history_entry["view"]
            region = history_entry["region"]

            print("<", region)

            window.focus_view(view)

            view.sel().clear()
            view.sel().add(region)
            view.show(region, True)

            # Clear jump position whenever
            # jumping to the last entry in the history.
            if _pos == 0:
                del jump_pos[window.id()]
            else:
                jump_pos[window.id()] = _pos

