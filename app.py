import streamlit as st
import pandas as pd
import json
from streamlit_gsheets import GSheetsConnection
from openai import OpenAI

# 1. SETUP AI & DATABASE
client = OpenAI(api_key=st.secrets["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1")
conn = st.connection("gsheets", type=GSheetsConnection)

SPREADSHEET_ID = "https://docs.google.com/spreadsheets/d/1GV_-EKGctK81G4His80Eoj1TnhKxM16FMfUfdMK5Yso/edit" 
df = conn.read(spreadsheet=SPREADSHEET_ID, usecols=list(range(9)))

# --- BULLETPROOF CLEANUP ---
df.columns = df.columns.str.strip()
df = df.dropna(subset=["question_id"])
df["difficulty_score"] = df["difficulty_score"].astype(str).str.replace(',', '.')
df["difficulty_score"] = pd.to_numeric(df["difficulty_score"], errors="coerce")
df = df.dropna(subset=["difficulty_score"])

# Make sure our new choice_counts column is ready to hold data
df["choice_counts"] = df["choice_counts"].fillna("{}").astype(str)

# 2. SETUP MEMORY
if "quiz_started" not in st.session_state:
    st.session_state.quiz_started = False  # Controls which page we see!
if "student_name" not in st.session_state:
    st.session_state.student_name = ""
if "student_id" not in st.session_state:
    st.session_state.student_id = ""
if "skill_level" not in st.session_state:
    st.session_state.skill_level = 0.50
if "skill_history" not in st.session_state:
    st.session_state.skill_history = [0.50] # Memory for the line chart
if "seen_questions" not in st.session_state:
    st.session_state.seen_questions = []
if "current_question_index" not in st.session_state:
    st.session_state.current_question_index = None
if "answered" not in st.session_state:
    st.session_state.answered = False
if "is_correct" not in st.session_state:
    st.session_state.is_correct = None
if "ai_explanation" not in st.session_state:
    st.session_state.ai_explanation = None

# ==========================================
# VIEW 1: THE START PAGE
# ==========================================
if not st.session_state.quiz_started:
    st.title("HKU Adaptive Physics Quiz")
    st.write("Welcome! Please enter your details to begin.")
    
    # Input fields for student info
    name_input = st.text_input("Full Name")
    id_input = st.text_input("Student ID")
    
    if st.button("Start Quiz"):
        if name_input and id_input: # Check if they actually typed something
            st.session_state.student_name = name_input
            st.session_state.student_id = id_input
            st.session_state.quiz_started = True
            st.rerun() # Instantly swap to the Quiz Page
        else:
            st.warning("Please enter both your Name and Student ID to continue.")

# ==========================================
# VIEW 2: THE QUIZ PAGE
# ==========================================
else:
    st.title(f"HKU Physics Quiz")
    st.write(f"Student: **{st.session_state.student_name}** ({st.session_state.student_id})")
    
    # --- VISUAL PROGRESS DASHBOARD ---
    total_questions = len(df)
    answered_count = len(st.session_state.seen_questions)
    
    # Calculate the current question number (and stop it from saying 71/70 at the end)
    current_q_num = min(answered_count + 1, total_questions)
    
    # Create two columns for a clean side-by-side layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.write(f"**Question:** {current_q_num} / {total_questions}")
        # Progress bar based on completion percentage
        st.progress(answered_count / total_questions)
        
    with col2:
        st.write(f"**Skill Level:** {round(st.session_state.skill_level, 2)}")
        # Progress bar based on skill (clamped between 0.0 and 1.0)
        safe_skill = min(1.0, max(0.0, st.session_state.skill_level))
        st.progress(safe_skill)
    
    # The Line Chart (hidden in an expander to keep the screen clean)
    with st.expander("📈 View Skill Growth Chart"):
        st.line_chart(st.session_state.skill_history)
    
    st.divider() # A nice horizontal line to separate the progress from the question

    # 3. ADAPTIVE LOGIC
    if st.session_state.current_question_index is None:
        unseen_df = df[~df['question_id'].isin(st.session_state.seen_questions)]
        
        if unseen_df.empty:
            st.success(f"🎉 Fantastic job, {st.session_state.student_name}! You have completed all available questions.")
            st.stop()
        else:
            unseen_df['skill_gap'] = abs(unseen_df['difficulty_score'] - st.session_state.skill_level)
            best_match_index = unseen_df['skill_gap'].idxmin()
            st.session_state.current_question_index = best_match_index

    # 4. DISPLAY QUESTION
    current_idx = st.session_state.current_question_index
    question_row = df.loc[current_idx]

    st.subheader(question_row["question_text"])
    
    # --- NEW IMAGE LOGIC ---
    # Check if the image_url column exists, is not empty, and is not a blank space
    if "image_url" in question_row and pd.notna(question_row["image_url"]) and str(question_row["image_url"]).strip() != "":
        st.image(str(question_row["image_url"]).strip())
    # -----------------------

    options_list = [opt.strip() for opt in question_row["options"].split(",")]
    student_choice = st.radio("Select your answer:", options_list, key=f"radio_{current_idx}")

    # 5. SUBMIT BUTTON & DATABASE UPDATE
    if not st.session_state.answered:
        if st.button("Submit"):
            st.session_state.answered = True
            st.session_state.seen_questions.append(question_row["question_id"])
            
            # 1. Update Total Attempts
            df.at[current_idx, 'total_attempts'] += 1
            
            # 2. Track the exact choice they made for your analysis!
            try:
                counts = json.loads(df.at[current_idx, 'choice_counts'])
            except:
                counts = {} # If it's empty, start a new dictionary
                
            # --- NEW LETTER MAPPING LOGIC ---
            # Find the position of their choice and assign it a letter
            choice_index = options_list.index(student_choice)
            letter_mapping = ["A", "B", "C", "D", "E", "F"] 
            letter_choice = letter_mapping[choice_index]
            
            if letter_choice in counts:
                counts[letter_choice] += 1
            else:
                counts[letter_choice] = 1
                
            # Save the dictionary back to the dataframe
            df.at[current_idx, 'choice_counts'] = json.dumps(counts)
            
            # 3. Check if they were correct
            if str(student_choice).strip() == str(question_row["correct_answer"]).strip():
                st.session_state.is_correct = True
                st.session_state.skill_level = min(1.0, st.session_state.skill_level + 0.15)
                df.at[current_idx, 'correct_attempts'] += 1
            else:
                st.session_state.is_correct = False
                st.session_state.skill_level = max(0.0, st.session_state.skill_level - 0.15)
            
            st.session_state.skill_history.append(st.session_state.skill_level)
            
            # 4. Recalculate difficulty & Save to Google Sheets
            new_difficulty = 1.0 - (df.at[current_idx, 'correct_attempts'] / df.at[current_idx, 'total_attempts'])
            df.at[current_idx, 'difficulty_score'] = round(new_difficulty, 2)
            
            conn.update(spreadsheet=SPREADSHEET_ID, data=df)
            st.cache_data.clear() # SUPER IMPORTANT: Forces Streamlit to clear its memory and actually push the save!
            
            st.rerun()

    # 6. AFTER SUBMIT: FEEDBACK, AI BUTTON, AND NEXT QUESTION
    if st.session_state.answered:
        if st.session_state.is_correct:
            st.success("Correct! Excellent job.")
        else:
            st.error(f"Incorrect. The correct answer was {question_row['correct_answer']}.")
            
            if st.button("🤖 Ask AI Tutor for Help"):
                with st.spinner("The AI Tutor is analyzing your answer..."):
                    prompt = f"""
                    The student guessed {student_choice} instead of {question_row['correct_answer']} for the following question: 
                    "{question_row['question_text']}"
                    Briefly explain why they are wrong.
                    CRITICAL FORMATTING RULE: 
                    You MUST use $ for inline math and $$ for standalone math blocks. 
                    Absolutely DO NOT use [ ], \[ \], or \( \) for math equations.
                    """
                    response = client.chat.completions.create(
                        model="openai/gpt-oss-120b:free", 
                        messages=[{"role": "system", "content": "You are a helpful university physics tutor."}, {"role": "user", "content": prompt}]
                    )
                    
                    # The Python Safety Net
                    raw_text = response.choices[0].message.content
                    clean_text = raw_text.replace("\\[", "$$").replace("\\]", "$$").replace("\\(", "$").replace("\\)", "$")
                    clean_text = clean_text.replace("[ ", "$$ ").replace(" ]", " $$")
                    
                    st.session_state.ai_explanation = clean_text
            
            if st.session_state.ai_explanation:
                st.info(st.session_state.ai_explanation)

        if st.button("Next Question"):
            st.session_state.current_question_index = None
            st.session_state.answered = False
            st.session_state.is_correct = None
            st.session_state.ai_explanation = None
            st.rerun()
