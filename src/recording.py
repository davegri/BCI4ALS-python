import numpy as np
from Marker import Marker
from board import Board

from psychopy import sound, visual

from pipeline import get_epochs, evaluate_pipeline
from data_utils import load_rec_params, save_raw, load_hyperparams
import spectral
import os

BG_COLOR = "black"
STIM_COLOR = "white"

visual = None
core = None
event = None


def run_session(params, retrain_pipeline=spectral, predict_pipeline=None, epochs=None, labels=None):
    """
    Run a recording session, if pipeline is passed display prediction after every epoch
    """

    # import psychopy only here to prevent pygame loading.
    from psychopy import visual as vis, core as cor, event as eve
    global visual, core, event
    visual, core, event = vis, cor, eve

    # create list of random trials
    trial_markers = Marker.all() * params["trials_per_stim"]
    np.random.shuffle(trial_markers)

    # open psychopy window and display starting message
    win = visual.Window(units="norm", color=BG_COLOR, fullscr=params["full_screen"])
    msg1 = f'Hello {params["subject"]}!\n Hit any key to start, press Esc at any point to exit'
    loop_through_messages(win, [msg1])

    if retrain_pipeline:
        hyperparams = load_hyperparams(params["subject"], retrain_pipeline)
        predict_pipeline = retrain_pipeline.create_pipeline(hyperparams)
        predict_pipeline.fit(epochs, labels)
        best_score = evaluate_pipeline(predict_pipeline, epochs, labels)

    # Start recording
    with Board(use_synthetic=params["use_synthetic_board"]) as board:
        for i, marker in enumerate(trial_markers):
            # "get ready" period
            show_stim_for_duration(win, progress_text(win, i + 1, len(trial_markers), marker),
                                   progress_sound(marker), params["get_ready_duration"])
            # calibration period
            core.wait(params["calibration_duration"])

            # motor imagery period
            board.insert_marker(marker)
            show_stim_with_beeps(win, marker_stim(win, marker), params["trial_duration"])

            if predict_pipeline:
                # We need to wait a short time between the end of the trial and trying to get it's data to make sure
                # that we have recorded (trial_duration * sfreq) samples after the latest marker (otherwise the epoch
                # will be too short)
                core.wait(0.5)

                # get latest epoch and make prediction
                raw = board.get_data()
                new_epochs, new_labels = get_epochs([raw], params["trial_duration"], params["calibration_duration"],
                                                    on_missing='ignore')
                new_epochs = new_epochs.get_data()
                prediction = predict_pipeline.predict(new_epochs)[-1]

                # display prediction result
                show_stim_for_duration(win, classification_result_txt(win, marker, prediction),
                                       classification_result_sound(marker, prediction),
                                       params["display_online_result_duration"])

            if retrain_pipeline and i % params["retrain_num"] == 0 and i != 0:
                text_stim(win, "Retraining model, please wait...").draw()
                win.flip()

                # train new pipeline
                total_epochs = np.concatenate((epochs, new_epochs), axis=0)
                total_labels = np.concatenate((labels, new_labels), axis=0)
                new_pipeline = retrain_pipeline.create_pipeline(hyperparams)
                new_pipeline.fit(total_epochs, total_labels)

                # evaluate new pipeline
                score = evaluate_pipeline(new_pipeline, total_epochs, total_labels)
                msg = f'Finished retraining \nold model score: {best_score} \nnew model score: {score}'
                win.flip()
                predict_pipeline = new_pipeline

                if score > best_score:
                    best_score = score
                    msg += "\nNice! the model has improved!"
                else:
                    msg += "\nNo improvement, Focus man.."
                msg += "\n Press any key to continue, ESC to exit"

                text_stim(win, msg).draw()
                win.flip()
                keys_pressed = event.waitKeys()
                if 'escape' in keys_pressed:
                    core.quit()

        core.wait(0.5)
        win.close()
        raw = board.get_data()
    save_raw(raw, rec_params)


def loop_through_messages(win, messages):
    for msg in messages:
        visual.TextStim(win=win, text=msg, color=STIM_COLOR).draw()
        win.flip()
        keys_pressed = event.waitKeys()
        if 'escape' in keys_pressed:
            core.quit()
        if 'backspace' in keys_pressed:
            break


def marker_stim(win, marker):
    shape = visual.ShapeStim(win, vertices=Marker(marker).shape, fillColor=STIM_COLOR, size=.5)
    return shape


def show_stim_for_duration(win, vis_stim, aud_stim, duration):
    # Adding this code here is an easy way to make sure we check for an escape event before showing every stimulus
    if 'escape' in event.getKeys():
        core.quit()

    vis_stim.draw()  # draw stim on back buffer
    aud_stim.play()
    win.flip()  # flip the front and back buffers and then clear the back buffer
    core.wait(duration)
    win.flip()  # flip back to the (now empty) back buffer


def text_stim(win, text):
    return visual.TextStim(win=win, text=text, color=STIM_COLOR, bold=True, alignHoriz='center', alignVert='center')


def show_stim_with_beeps(win, vis_stim, duration):
    # Adding this code here is an easy way to make sure we check for an escape event before showing every stimulus
    if 'escape' in event.getKeys():
        core.quit()

    vis_stim.draw()  # draw stim on back buffer
    sound.Sound("a", secs=0.1).play()
    win.flip()  # flip the front and back buffers and then clear the back buffer
    core.wait(duration)
    sound.Sound("c", secs=0.1).play()
    win.flip()  # flip back to the (now empty) back buffer


def progress_text(win, done, total, stim):
    txt = visual.TextStim(win=win, text=f'trial {done}/{total}\n get ready for {Marker(stim).name}', color=STIM_COLOR,
                          bold=True, alignHoriz='center', alignVert='center')

    txt.font = 'arial'
    return txt


def progress_text(win, done, total, stim):
    return text_stim(win, f'trial {done}/{total}\n get ready for {Marker(stim).name}')


def progress_sound(stim):
    return sound.Sound(os.path.join("../audio", f"{Marker(stim).name}.ogg"))


def classification_result_sound(marker, prediction):
    if marker == prediction:
        return sound.Sound(os.path.join("../audio", "good job!.ogg"))
    return sound.Sound(os.path.join("../audio", "try again.ogg"))


def classification_result_txt(win, marker, prediction):
    if marker == prediction:
        msg = 'correct prediction'
        col = (0, 1, 0)
    else:
        msg = 'incorrect prediction'
        col = (1, 0, 0)
    return visual.TextStim(win=win, text=f'label: {Marker(marker).name}\nprediction: {Marker(prediction).name}\n{msg}',
                           color=col,
                           bold=True, alignHoriz='center', alignVert='center', font='arial', )


def marker_image(win, marker):
    return visual.ImageStim(win=win, image=Marker(marker).image_path, units="norm", size=2, color=(1, 1, 1))


if __name__ == "__main__":
    rec_params = load_rec_params()
    record_data(rec_params)
