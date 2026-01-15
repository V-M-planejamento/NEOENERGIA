import json
import os
import streamlit as st

NOTES_FILE = "gantt_notes.json"

def load_notes():
    """Carrega as notas do arquivo JSON."""
    if not os.path.exists(NOTES_FILE):
        return {}
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao carregar notas: {e}")
        return {}

def save_note(project, task, note_text):
    """Salva uma nota para uma tarefa específica de um projeto."""
    try:
        notes = load_notes()
        key = f"{project}|{task}"
        notes[key] = note_text
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erro ao salvar nota: {e}")
        return False

def get_note(project, task):
    """Recupera a nota de uma tarefa específica."""
    notes = load_notes()
    return notes.get(f"{project}|{task}", "")
