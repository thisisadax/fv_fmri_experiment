#!/usr/bin/env python
import argparse
import random
import sys
from datetime import datetime
from pathlib import Path

from psychopy import visual, core, event, logging

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
from utils import (Scanner, EventLogger, load_run_data,
                   create_output_directory, save_experiment_data)


class AnalogyExperiment:
    def __init__(self, subject, session, run, language, mode,
                 baseline_mode='fixation', fixed_block_duration=False):
        self.p_info = {
            'subject': subject, 'session': session,
            'run': run, 'language': language
        }
        self.mode = mode
        self.baseline_mode = baseline_mode
        self.fixed_block_duration = fixed_block_duration
        self.win = None
        self.stim = {}

        # Output Setup (one timestamp for log + behavioral exports)
        self.out_dir = create_output_directory(subject, session, run, language)
        self.run_ts = datetime.now().strftime("%y%m%d%H%M%S")
        logging.LogFile(
            str(self.out_dir / f"experiment_{self.run_ts}.log"),
            level=logging.DATA,
            filemode="w",
        )

        # Init Window
        self.win = visual.Window(
            size=cfg.WINDOW_SIZE, fullscr=cfg.FULLSCREEN, screen=1,
            monitor=cfg.MONITOR_NAME, units=cfg.UNITS, color=cfg.BACKGROUND_COLOR,
            waitBlanking=True, allowGUI=False
        )

        # Use language-appropriate font
        font = cfg.FONT_NAME_KOREAN if language == 'korean' else cfg.FONT_NAME
        self.scanner = Scanner(
            self.win, mode=self.mode,
            tr=cfg.SCANNER_SETTINGS['TR'],
            sync_key=cfg.SCANNER_SETTINGS['sync'],
            font=font
        )
        self.logger = EventLogger()
        self.blocks = load_run_data(language, subject, session, run)
        self._init_stimuli()

    def _init_stimuli(self):
        """Create stimuli with precise text alignment metrics."""
        S = self.stim
        is_korean = self.p_info['language'] == 'korean'

        font = cfg.FONT_NAME_KOREAN if is_korean else cfg.FONT_NAME
        space_width = cfg.WORD_HEIGHT * 0.6
        spacing_chars = len(cfg.COLON_SPACING)
        self.word_offset_x = (0.5 * space_width) + (spacing_chars * space_width)
        txt_args = {'win': self.win, 'font': font, 'color': cfg.TEXT_COLOR, 'alignText': 'center'}

        instr_height = 0.035 if is_korean else 0.03
        hint_height = 0.022 if is_korean else 0.02

        S['instr'] = visual.TextStim(
            text='', height=instr_height, units='height', wrapWidth=1.5,
            **txt_args
        )
        S['hint'] = visual.TextStim(
            win=self.win, font=font,
            text=cfg.CONTINUE_HINT_TEXT[self.p_info['language']],
            units='height', height=hint_height, pos=(0, -0.40),
            color=[0.4, 0.4, 0.4], alignText='center'
        )
        S['fixation'] = visual.TextStim(
            win=self.win, text='+', height=cfg.FIXATION_SIZE, font=cfg.FONT_NAME
        )
        S['colon'] = visual.TextStim(text=':', height=cfg.WORD_HEIGHT, **txt_args)
        S['word_L'] = visual.TextStim(text='', height=cfg.WORD_HEIGHT, **txt_args)
        S['word_R'] = visual.TextStim(text='', height=cfg.WORD_HEIGHT, **txt_args)
        S['opt_up'] = visual.TextStim(
            text='', pos=(0, cfg.AFC_OPTION_Y), height=cfg.WORD_HEIGHT, **txt_args
        )
        S['opt_lo'] = visual.TextStim(
            text='', pos=(0, -cfg.AFC_OPTION_Y), height=cfg.WORD_HEIGHT, **txt_args
        )

    def _get_word_pos(self, word, side, start_x=0.0):
        """Calculates precise X-coordinate to align text edges to the colon/center."""
        char_width = cfg.WORD_HEIGHT * (1.0 if self.p_info['language'] == 'korean' else 0.6)
        width = len(word) * char_width
        if side == 'left':
            return -self.word_offset_x - (width / 2.0)
        elif side == 'right':
            return self.word_offset_x + (width / 2.0)
        elif side == 'option':
            return start_x + (width / 2.0)
        return 0.0

    def show_instructions(self):
        """Displays instructions line-by-line, waiting for input."""
        full_text = cfg.INSTRUCTIONS[self.p_info['language']]
        lines = full_text.split('\n')
        if lines and not lines[0].strip():
            lines = lines[1:]

        current_text = ""
        for line in lines:
            current_text += line + "\n"
            if line.strip():
                self.stim['instr'].text = current_text.strip()
                self.stim['instr'].draw()
                self.stim['hint'].draw()
                self.win.flip()
                keys = event.waitKeys(keyList=['1', '2', 'space', 'enter', 'return', 'escape'])
                if 'escape' in keys:
                    self._close()

    def _draw_pair(self, w1, w2=None):
        """Draws word pair (or single word) with correct alignment."""
        self.stim['word_L'].text = w1
        self.stim['word_L'].pos = (self._get_word_pos(w1, 'left'), 0)
        self.stim['word_L'].draw()
        self.stim['colon'].draw()
        if w2:
            self.stim['word_R'].text = w2
            self.stim['word_R'].pos = (self._get_word_pos(w2, 'right'), 0)
            self.stim['word_R'].draw()
        self.win.flip()

    def run_2afc(self, target, distractor, word1):
        """Run 2AFC trial segment with response timeout."""
        is_upper = random.choice([True, False])
        up_txt, lo_txt = (target, distractor) if is_upper else (distractor, target)
        corr_btn = cfg.BUTTON_UPPER if is_upper else cfg.BUTTON_LOWER

        # Option positioning
        self.stim['opt_up'].text = up_txt
        self.stim['opt_up'].pos = (
            self._get_word_pos(up_txt, 'option', self.word_offset_x),
            cfg.AFC_OPTION_Y
        )
        self.stim['opt_lo'].text = lo_txt
        self.stim['opt_lo'].pos = (
            self._get_word_pos(lo_txt, 'option', self.word_offset_x),
            -cfg.AFC_OPTION_Y
        )

        # Draw static elements (Word 1 + Colon + Options)
        self.stim['word_L'].text = word1
        self.stim['word_L'].pos = (self._get_word_pos(word1, 'left'), 0)
        self.stim['word_L'].draw()
        self.stim['colon'].draw()
        self.stim['opt_up'].draw()
        self.stim['opt_lo'].draw()
        self.win.flip()

        # Response loop
        t0 = self.logger.clock.getTime()
        timeout_at = t0 + cfg.MAX_RESPONSE_TIME
        event.clearEvents()

        while True:
            self.scanner.check_for_tr()
            now = self.logger.clock.getTime()

            # Timeout: automatically proceed with no response
            if now >= timeout_at:
                logging.data(
                    f"2AFC timeout at {now:.4f}s "
                    f"(limit={cfg.MAX_RESPONSE_TIME:.3f}s)"
                )
                return {
                    'rt': None,
                    'key': None,
                    'corr': False,
                    'chosen': None,
                    'timeout': True,
                }

            keys = event.getKeys(timeStamped=self.logger.clock)
            for key, t in keys:
                if key in cfg.QUIT_KEYS:
                    self._close()
                if key in cfg.RESPONSE_KEYS:
                    return {
                        'rt': t - t0,
                        'key': key,
                        'corr': (key == corr_btn),
                        'chosen': up_txt if key == cfg.BUTTON_UPPER else lo_txt,
                        'timeout': False,
                    }

            core.wait(0.001)

    def _wait_for_block_end(self, block_onset):
        """Show fixation for the remainder of BLOCK_DURATION after the probe response."""
        target_time = block_onset + cfg.BLOCK_DURATION
        delay = target_time - self.logger.clock.getTime()
        if delay > 0:
            self.stim['fixation'].draw()
            self.win.flip()
            core.wait(delay)

    def execute_relation_block(self, block):
        onset = self.logger.clock.getTime()

        # Present Examples
        for w1, w2 in block.examples:
            self._draw_pair(w1)
            core.wait(cfg.WORD_DURATION)
            self._draw_pair(w1, w2)
            core.wait(cfg.WORD_DURATION)
            self.stim['fixation'].draw()
            self.win.flip()
            core.wait(cfg.ISI)

        # Present Probe
        probe = block.probe
        w1 = probe['word1']
        opt1 = probe['opt1']
        opt2 = probe['opt2']
        target_str = opt1 if probe['corr_ans'] == 1 else opt2
        distractor_str = opt2 if probe['corr_ans'] == 1 else opt1

        self._draw_pair(w1)
        core.wait(cfg.WORD_DURATION)
        resp = self.run_2afc(target=target_str, distractor=distractor_str, word1=w1)

        if self.fixed_block_duration:
            self._wait_for_block_end(onset)

        dur = self.logger.clock.getTime() - onset
        self.logger.log_trial(
            trial_idx=block.block_idx,
            onset=onset,
            duration=dur,
            trial_type=block.trial_type,
            response_time=resp['rt'],
            response_correct=resp['corr'],
            response_chosen=resp['chosen'],
            correct_answer=target_str,
            response_key=resp['key'],
            response_timeout=resp['timeout'],
        )

    def execute_baseline_block(self, block):
        onset = self.logger.clock.getTime()

        if self.baseline_mode == 'structured':
            lang = self.p_info['language']
            bt = cfg.BASELINE_TRIALS[lang]
            for w1, w2 in bt['examples']:
                self._draw_pair(w1)
                core.wait(cfg.WORD_DURATION)
                self._draw_pair(w1, w2)
                core.wait(cfg.WORD_DURATION)
                self.stim['fixation'].draw()
                self.win.flip()
                core.wait(cfg.ISI)

            probe = bt['probe']
            self._draw_pair(probe['word1'])
            core.wait(cfg.WORD_DURATION)
            resp = self.run_2afc(
                target=probe['option_1'],
                distractor=probe['option_2'],
                word1=probe['word1'],
            )

            if self.fixed_block_duration:
                self._wait_for_block_end(onset)

            dur = self.logger.clock.getTime() - onset
            self.logger.log_trial(
                trial_idx=block.block_idx,
                onset=onset,
                duration=dur,
                trial_type='baseline',
                response_time=resp['rt'],
                response_correct=resp['corr'],
                response_chosen=resp['chosen'],
                correct_answer=None,
                response_key=resp['key'],
                response_timeout=resp['timeout'],
            )
        else:
            self.stim['fixation'].draw()
            self.win.flip()
            core.wait(cfg.BLOCK_DURATION)
            dur = self.logger.clock.getTime() - onset
            self.logger.log_trial(
                trial_idx=block.block_idx,
                onset=onset,
                duration=dur,
                trial_type='baseline',
                response_time=None,
                response_correct=None,
                response_chosen=None,
                correct_answer=None,
                response_key=None,
                response_timeout=False,
            )

    def run(self):
        try:
            if self.p_info['run'] == 1:
                self.show_instructions()

            self.scanner.wait_for_start()
            self.logger.start()

            self.stim['fixation'].draw()
            self.win.flip()
            self.scanner.wait_for_next_tr()

            for block in self.blocks:
                if block.block_type == 'baseline':
                    self.execute_baseline_block(block)
                else:
                    self.execute_relation_block(block)

            scored = [
                t for t in self.logger.trials
                if t.get('trial_type') != 'baseline'
                and t.get('response_correct') is not None
            ]
            n_correct = sum(1 for t in scored if t['response_correct'])
            n_total = len(scored)
            acc = (n_correct / n_total * 100) if n_total else 0.0
            print(f"Run accuracy (excluding baseline): {acc:.1f}% ({n_correct}/{n_total})")

            self.stim['instr'].text = cfg.END_TEXT[self.p_info['language']]
            self.stim['instr'].draw()
            self.win.flip()
            core.wait(3.0)
        finally:
            self._close()

    def _close(self):
        """Cleanup and save data."""
        try:
            logging.info("Saving data...")
            save_experiment_data(
                self.out_dir, self.logger, run_ts=self.run_ts, **self.p_info
            )
        except Exception as e:
            logging.error(f"Failed to save data: {e}")
        if self.win:
            self.win.close()
            core.quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--subject', '-p', required=True)
    parser.add_argument('--session', '-s', type=int, required=True)
    parser.add_argument('--run', '-r', type=int, required=True)
    parser.add_argument('--language', '-l', default='korean')
    parser.add_argument('--mode', '-m', default='Scan', choices=['Scan', 'Test'])
    parser.add_argument('--baseline', '-b', default='fixation',
                        choices=['fixation', 'structured'])
    parser.add_argument('--fixed-block-duration', action='store_true', default=False,
                        help='Pad each block to BLOCK_DURATION with fixation before '
                             'starting the next block. Default: proceed immediately '
                             'after the probe response.')
    args = parser.parse_args()

    exp = AnalogyExperiment(
        subject=args.subject,
        session=args.session,
        run=args.run,
        language=args.language,
        mode=args.mode,
        baseline_mode=args.baseline,
        fixed_block_duration=args.fixed_block_duration,
    )
    exp.run()