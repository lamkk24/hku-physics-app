import streamlit as st
import pandas as pd
import json
import time
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
df["choice_counts"] = df["choice_counts"].fillna("{}").astype(str)

# 2. SETUP MEMORY
if "quiz_started" not in st.session_state:
    st.session_state.quiz_started = False
if "admin_mode" not in st.session_state:
    st.session_state.admin_mode = False
if "student_name" not in st.session_state:
    st.session_state.student_name = ""
if "student_id" not in st.session_state:
    st.session_state.student_id = ""
if "skill_level" not in st.session_state:
    st.session_state.skill_level = 0.50
if "skill_history" not in st.session_state:
    st.session_state.skill_history = [0.50]
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
if "session_score" not in st.session_state:
    st.session_state.session_score = 0
if "student_choices" not in st.session_state:
    st.session_state.student_choices = []
if "record_saved" not in st.session_state:
    st.session_state.record_saved = False
# --- NEW MEMORY FOR REVIEW & TIMER ---
if "wrong_answers" not in st.session_state:
    st.session_state.wrong_answers = [] 
if "start_time" not in st.session_state:
    st.session_state.start_time = None

# Exam Settings
MAX_QUESTIONS = 20
TIME_LIMIT_SECONDS = 30 * 60 # 30 minutes

# ==========================================
# VIEW 1: THE START PAGE
# ==========================================
if not st.session_state.quiz_started and not st.session_state.admin_mode:
    st.title("HKU Adaptive Physics Quiz")
    st.write("Welcome! Please enter your details to begin.")
    
    name_input = st.text_input("Full Name")
    id_input = st.text_input("Student ID")
    
    if st.button("Start Quiz"):
        # Secret Admin Login
        if name_input == "ADMIN" and id_input == "SECRET":
            st.session_state.admin_mode = True
            st.rerun()
        elif name_input and id_input:
            st.session_state.student_name = name_input
            st.session_state.student_id = id_input
            st.session_state.quiz_started = True
            st.session_state.start_time = time.time() # Start the timer!
            st.rerun()
        else:
            st.warning("Please enter both your Name and Student ID to continue.")

# ==========================================
# VIEW 2: THE ADMIN DASHBOARD
# ==========================================
elif st.session_state.admin_mode:
    st.title("👨‍🏫 Teacher Analytics Dashboard")
    
    # Pull live gradebook data
    records_df = conn.read(spreadsheet=SPREADSHEET_ID, worksheet="Student Records")
    
    st.write("### Live Student Records")
    st.dataframe(records_df)
    
    if st.button("Logout"):
        st.session_state.admin_mode = False
        st.rerun()

# ==========================================
# VIEW 3: THE QUIZ PAGE
# ==========================================
else:
    st.title(f"HKU Physics Quiz")
    
    # --- TIME CALCULATION ---
    elapsed_time = time.time() - st.session_state.start_time
    time_left = max(0, TIME_LIMIT_SECONDS - elapsed_time)
    mins, secs = divmod(int(time_left), 60)
    time_display = f"{mins:02d}:{secs:02d}"
    
    # --- VISUAL PROGRESS DASHBOARD ---
    total_questions = min(MAX_QUESTIONS, len(df))
    answered_count = len(st.session_state.seen_questions)
    current_q_num = min(answered_count + 1, total_questions)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write(f"**Question:** {current_q_num} / {total_questions}")
        st.progress(min(1.0, answered_count / total_questions))
    with col2:
        st.write(f"**Skill:** {round(st.session_state.skill_level, 2)}")
        st.progress(min(1.0, max(0.0, st.session_state.skill_level)))
    with col3:
        # Change color to red if they have less than 5 minutes left
        if time_left <= 300: 
            st.write(f"**⏱️ Time Left:** :red[{time_display}]")
        else:
            st.write(f"**⏱️ Time Left:** {time_display}")
            
    st.divider()

    # 3. ADAPTIVE LOGIC
    if st.session_state.current_question_index is None:
        unseen_df = df[~df['question_id'].isin(st.session_state.seen_questions)]
        
        # STOP CONDITION: Out of questions, hit limit, OR out of time
        if unseen_df.empty or answered_count >= MAX_QUESTIONS or time_left <= 0:
            
            # Save to Gradebook
            if not st.session_state.record_saved:
                records_df = conn.read(spreadsheet=SPREADSHEET_ID, worksheet="Student Records")
                new_record = pd.DataFrame([{
                    "Name": st.session_state.student_name,
                    "Student ID": st.session_state.student_id,
                    "Score": f"{st.session_state.session_score} / {answered_count}",
                    "Questions Asked": ", ".join(st.session_state.seen_questions),
                    "Answers Given": ", ".join(st.session_state.student_choices)
                }])
                updated_records = pd.concat([records_df, new_record], ignore_index=True)
                conn.update(spreadsheet=SPREADSHEET_ID, worksheet="Student Records", data=updated_records)
                st.cache_data.clear()
                st.session_state.record_saved = True
            
            if time_left <= 0:
                st.error("⏳ Time is up!")
            else:
                st.success(f"🎉 Fantastic job, {st.session_state.student_name}! You scored {st.session_state.session_score} / {answered_count}.")
            
            # --- POST-QUIZ REVIEW ---
            if len(st.session_state.wrong_answers) > 0:
                st.write("### 📝 Let's review the questions you missed:")
                for idx, wrong in enumerate(st.session_state.wrong_answers):
                    with st.expander(f"Review Question {idx+1}"):
                        st.write(f"**Question:** {wrong['question']}")
                        st.write(f"❌ **You answered:** {wrong['student']}")
                        st.write(f"✅ **Correct answer:** {wrong['correct']}")
            else:
                st.write("Wow, a perfect score! Nothing to review.")
            
            if st.button("🏠 Return to Start Page"):
                st.session_state.quiz_started = False
                st.session_state.student_name = ""
                st.session_state.student_id = ""
                st.session_state.skill_level = 0.50
                st.session_state.skill_history = [0.50]
                st.session_state.seen_questions = []
                st.session_state.current_question_index = None
                st.session_state.answered = False
                st.session_state.is_correct = None
                st.session_state.ai_explanation = None
                st.session_state.session_score = 0
                st.session_state.student_choices = []
                st.session_state.record_saved = False
                st.session_state.wrong_answers = []
                st.session_state.start_time = None
                st.rerun()
            st.stop()
        else:
            unseen_df['skill_gap'] = abs(unseen_df['difficulty_score'] - st.session_state.skill_level)
            best_match_index = unseen_df['skill_gap'].idxmin()
            st.session_state.current_question_index = best_match_index

    # 4. DISPLAY QUESTION
    current_idx = st.session_state.current_question_index
    question_row = df.loc[current_idx]

    st.subheader(question_row["question_text"])
    
    img_url = str(question_row.get("image_url", "")).strip()
    if img_url.startswith("http"):
        st.image(img_url)

    options_list = [opt.strip() for opt in question_row["options"].split(",")]
    student_choice = st.radio("Select your answer:", options_list, key=f"radio_{current_idx}")

    # 5. SUBMIT BUTTON & DATABASE UPDATE
    if not st.session_state.answered:
        if st.button("Submit"):
            st.session_state.answered = True
            st.session_state.seen_questions.append(question_row["question_id"])
            
            df.at[current_idx, 'total_attempts'] += 1
            
            try:
                counts = json.loads(df.at[current_idx, 'choice_counts'])
            except:
                counts = {}
                
            choice_index = options_list.index(student_choice)
            letter_mapping = ["A", "B", "C", "D", "E", "F"] 
            letter_choice = letter_mapping[choice_index]
            st.session_state.student_choices.append(letter_choice)
            
            if letter_choice in counts:
                counts[letter_choice] += 1
            else:
                counts[letter_choice] = 1
                
            df.at[current_idx, 'choice_counts'] = json.dumps(counts)
            
            if str(student_choice).strip() == str(question_row["correct_answer"]).strip():
                st.session_state.is_correct = True
                st.session_state.skill_level = min(1.0, st.session_state.skill_level + 0.15)
                df.at[current_idx, 'correct_attempts'] += 1
                st.session_state.session_score += 1
            else:
                st.session_state.is_correct = False
                st.session_state.skill_level = max(0.0, st.session_state.skill_level - 0.15)
                
                # --- RECORD WRONG ANSWER FOR REVIEW ---
                st.session_state.wrong_answers.append({
                    "question": question_row["question_text"],
                    "student": student_choice,
                    "correct": question_row["correct_answer"]
                })
            
            st.session_state.skill_history.append(st.session_state.skill_level)
            
            new_difficulty = 1.0 - (df.at[current_idx, 'correct_attempts'] / df.at[current_idx, 'total_attempts'])
            df.at[current_idx, 'difficulty_score'] = round(new_difficulty, 2)
            
            conn.update(spreadsheet=SPREADSHEET_ID, data=df)
            st.cache_data.clear()
            
            st.rerun()

    # 6. AFTER SUBMIT
    if st.session_state.answered:
        if st.session_state.is_correct:
            st.success("Correct! Excellent job.")
        else:
            st.error(f"Incorrect. The correct answer was {question_row['correct_answer']}.")
            
            if st.button("🤖 Ask AI Tutor for Help"):
                with st.spinner("The AI Tutor is analyzing your answer..."):
                    hidden_context = ""
                    if "ai_context" in question_row and pd.notna(question_row["ai_context"]):
                        hidden_context = f"Image description for context: {question_row['ai_context']}"
                        
                    prompt = f"""
                    The student guessed {student_choice} instead of {question_row['correct_answer']} for the following question: 
                    "{question_row['question_text']}"
                    {hidden_context}
                    Briefly explain why they are wrong.
                    CRITICAL FORMATTING RULE: 
                    You MUST use $ for inline math and $$ for standalone math blocks. 
                    Absolutely DO NOT use [ ], \[ \], or \( \) for math equations.
                    """
                    response = client.chat.completions.create(
                        model="openai/gpt-oss-120b:free", 
                        messages=[{"role": "system", "content": "You are a helpful university physics tutor."}, {"role": "user", "content": prompt}]
                    )
                    
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
