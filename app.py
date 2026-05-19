import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from openai import OpenAI

# 1. SETUP AI & DATABASE
client = OpenAI(api_key=st.secrets["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1")
conn = st.connection("gsheets", type=GSheetsConnection)

# Read the live Google Sheet
# Replace 'YOUR_SPREADSHEET_ID' with the ID you saved in Step 1!
SPREADSHEET_ID = "https://docs.google.com/spreadsheets/d/1GV_-EKGctK81G4His80Eoj1TnhKxM16FMfUfdMK5Yso/edit?gid=0#gid=0" 
df = conn.read(spreadsheet=SPREADSHEET_ID, usecols=list(range(7)))

# --- NEW CLEANUP CODE ---
# 1. Throw away any blank rows from Google Sheets
df = df.dropna(subset=["question_id"])

# 2. Make sure Python treats the difficulty column as actual math numbers
df["difficulty_score"] = pd.to_numeric(df["difficulty_score"], errors="coerce")
# ------------------------

st.title("HKU Adaptive Physics Quiz")

# 2. SETUP MEMORY
if "skill_level" not in st.session_state:
    st.session_state.skill_level = 0.50 # Start the student at medium skill
if "seen_questions" not in st.session_state:
    st.session_state.seen_questions = [] # Track what they've already answered
if "current_question_index" not in st.session_state:
    st.session_state.current_question_index = None
if "answered" not in st.session_state:
    st.session_state.answered = False

# 3. ADAPTIVE LOGIC: Pick the best question
if st.session_state.current_question_index is None:
    # Filter out questions they already saw
    unseen_df = df[~df['question_id'].isin(st.session_state.seen_questions)]
    
    if unseen_df.empty:
        st.success("🎉 You have completed all available questions!")
        st.stop()
    else:
        # Math: Find the question difficulty that is closest to their current skill level
        unseen_df['skill_gap'] = abs(unseen_df['difficulty_score'] - st.session_state.skill_level)
        best_match_index = unseen_df['skill_gap'].idxmin()
        st.session_state.current_question_index = best_match_index

# 4. DISPLAY QUESTION
current_idx = st.session_state.current_question_index
question_row = df.loc[current_idx]

st.write(f"**Current Estimated Skill Level:** {round(st.session_state.skill_level, 2)}")
st.subheader(question_row["question_text"])

# Convert the string of options from Google Sheets into a list
options_list = [opt.strip() for opt in question_row["options"].split(",")]
student_choice = st.radio("Select your answer:", options_list, key=f"radio_{current_idx}")

# 5. SUBMIT BUTTON & DATABASE UPDATE
if not st.session_state.answered:
    if st.button("Submit"):
        st.session_state.answered = True
        st.session_state.seen_questions.append(question_row["question_id"])
        
        # Update Google Sheet Data Memory
        df.at[current_idx, 'total_attempts'] += 1
        
        if student_choice == question_row["correct_answer"]:
            st.success("Correct! Excellent job.")
            st.session_state.skill_level = min(1.0, st.session_state.skill_level + 0.15) # Increase skill
            df.at[current_idx, 'correct_attempts'] += 1
        else:
            st.error(f"Incorrect. The correct answer was {question_row['correct_answer']}.")
            st.session_state.skill_level = max(0.0, st.session_state.skill_level - 0.15) # Decrease skill
            
            with st.spinner("The AI Tutor is analyzing your answer..."):
                prompt = f"Student guessed {student_choice} instead of {question_row['correct_answer']} for '{question_row['question_text']}'. Briefly explain why they are wrong using $ for math."
                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b:free", 
                    messages=[{"role": "system", "content": "You are a physics tutor."}, {"role": "user", "content": prompt}]
                )
                st.info(response.choices[0].message.content)
        
        # Recalculate difficulty: 1.0 - (correct / total)
        new_difficulty = 1.0 - (df.at[current_idx, 'correct_attempts'] / df.at[current_idx, 'total_attempts'])
        df.at[current_idx, 'difficulty_score'] = round(new_difficulty, 2)
        
        # Save the updated math back to Google Sheets!
        conn.update(spreadsheet=SPREADSHEET_ID, data=df)
        
        st.rerun()

if st.session_state.answered:
    if st.button("Next Question"):
        st.session_state.current_question_index = None # Force it to pick a new question
        st.session_state.answered = False
        st.rerun()
