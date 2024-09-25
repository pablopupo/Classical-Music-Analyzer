from flask import Flask, request, redirect, url_for, render_template, flash
import os
from music21 import converter, environment, roman, meter, stream, instrument
import subprocess
from collections import Counter

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mid', 'midi', 'mscz'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'supersecretkey'  # Needed for flashing messages

# Configure music21 to use MuseScore
us = environment.UserSettings()
us['musicxmlPath'] = '/Applications/MuseScore 4.app/Contents/MacOS/mscore'  # Update this to the correct path
us['musescoreDirectPNGPath'] = '/Applications/MuseScore 4.app/Contents/MacOS/mscore'  # Update this to the correct path


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = file.filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(file_path)
            return redirect(url_for('uploaded_file', filename=filename))
        else:
            flash('File not allowed')
            return redirect(request.url)
    return render_template('upload.html')


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # Convert .mscz to .musicxml if necessary
    if file_path.endswith('.mscz'):
        musicxml_path = file_path.replace('.mscz', '.musicxml')
        command = [us['musicxmlPath'], file_path, '-o', musicxml_path]
        subprocess.run(command, check=True)
        file_path = musicxml_path

    try:
        midi = converter.parse(file_path)
    except Exception as e:
        flash(f'Error parsing file: {e}')
        return redirect(url_for('home'))

    key_signature = midi.analyze('key')
    tempo_indication = midi.metronomeMarkBoundaries()[0][2]
    time_signature = midi.getTimeSignatures()[0]

    # Extract instrument information
    instruments = set()
    for part in midi.parts:
        part_instruments = part.getElementsByClass(instrument.Instrument)
        if part_instruments:
            for instr in part_instruments:
                instrument_name = instr.instrumentName or type(instr).__name__
                instruments.add(instrument_name)
        elif part.partName:
            instruments.add(part.partName)

    # Remove duplicates and standardize instrument names
    instruments = set(instrument.strip() for instrument in instruments if instrument)

    # Replace generic "Piano" entries with a single "Piano" entry
    if any(instr.startswith("Piano") for instr in instruments):
        instruments = {instr for instr in instruments if not instr.startswith("Piano")}
        instruments.add("Piano")

    # Replace generic "Sampler" entries with a single "Sampler" entry
    if any(instr.startswith("Sampler") for instr in instruments):
        instruments = {instr for instr in instruments if not instr.startswith("Sampler")}
        instruments.add("Sampler")

    # Replace generic "Voice" entries with a single "Voice" entry
    if any(instr.startswith("Voice") for instr in instruments):
        instruments = {instr for instr in instruments if not instr.startswith("Voice")}
        instruments.add("Voice")

    # Replace generic "Electric Guitar" entries with a single "Electric Guitar" entry
    if any(instr.startswith("Electric Guitar") for instr in instruments):
        instruments = {instr for instr in instruments if not instr.startswith("Electric Guitar")}
        instruments.add("Electric Guitar")

    instruments = {instr for instr in instruments if not instr.startswith("0013GIVE:")}

    if not instruments:
        instruments.add("Unknown Instrument")

    # Step 1: Store notes by measure
    measure_notes = {}
    for part in midi.parts:
        measures = part.getElementsByClass("Measure")
        if not measures:
            continue

        for i, measure in enumerate(measures):
            notes = []
            for element in measure.flatten().notesAndRests:
                if element.isNote:
                    notes.append(element.nameWithOctave)
            if notes:
                measure_notes[i + 1] = notes  # Store measure number and notes

    # Step 2 and 3: Compare measures to find motifs
    motifs = {}
    for i, notes1 in measure_notes.items():
        for j, notes2 in measure_notes.items():
            if i != j and notes1 == notes2:
                if tuple(notes1) not in motifs:
                    motifs[tuple(notes1)] = []
                motifs[tuple(notes1)].append((i, j))

    # Filter motifs that appear in multiple places
    filtered_motifs = {k: v for k, v in motifs.items() if len(v) > 1}

    # Filter out percussion parts and analyze harmonies
    non_percussion_parts = []
    for part in midi.parts:
        instruments = part.getInstruments(returnDefault=True)
        if not any(instr.instrumentName and 'Percussion' in instr.instrumentName for instr in instruments):
            non_percussion_parts.append(part)

    # Convert non-percussion parts to a stream
    midi_no_percussion = stream.Score(non_percussion_parts)
    chords = midi_no_percussion.chordify()

    # Step 4: Harmonize and display motifs and harmonic structures
    harmonic_analysis = []
    for c in chords.flatten().getElementsByClass('Chord'):
        try:
            rn = roman.romanNumeralFromChord(c, key_signature)
            harmonic_analysis.append(rn.figure)
        except Exception as e:
            # Handle cases where Roman numeral analysis fails
            print(f"Error processing chord {c}: {e}")

    harmonic_analysis = list(dict.fromkeys(harmonic_analysis))

    return render_template('display.html', filename=filename,
                           key_signature=key_signature,
                           tempo_indication=tempo_indication,
                           time_signature=time_signature,
                           note_sequences=filtered_motifs,
                           harmonic_analysis=harmonic_analysis,
                           instruments=sorted(list(map(str, instruments))))


if __name__ == '__main__':
    app.run(debug=True)
