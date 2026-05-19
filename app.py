import streamlit as st
import json
from openai import OpenAI

# --- 1. SETUP AI ---
client = OpenAI(
    api_key=st.secrets["OPENROUTER_API_KEY"], # We replaced the text with a secret vault key
    base_url="https://openrouter.ai/api/v1" 
)

# --- 2. SETUP MEMORY (The "Sticky Notes") ---
# If this is the first time the page loads, create these sticky notes:
if "question_index" not in st.session_state:
    st.session_state.question_index = 0  # Start at the first question (0 in Python)
if "score" not in st.session_state:
    st.session_state.score = 0           # Start with a score of 0
if "answered" not in st.session_state:
    st.session_state.answered = False    # Track if they clicked submit yet

st.title("HKU Adaptive Physics Quiz")

# --- 3. LOAD DATABASE ---
with open("question_bank.json", "r") as file:
    questions = json.load(file)

# --- 4. CHECK IF THE QUIZ IS OVER ---
if st.session_state.question_index >= len(questions):
    st.success("🎉 You have completed the quiz!")
    st.write(f"Your final score is: {st.session_state.score} out of {len(questions)}")
    
    # Give them a button to restart
    if st.button("Restart Quiz"):
        st.session_state.question_index = 0
        st.session_state.score = 0
        st.session_state.answered = False
        st.rerun() # This forces Streamlit to refresh the page instantly

else:
    # --- 5. SHOW THE CURRENT QUESTION ---
    current_question = questions[st.session_state.question_index]
    
    st.write(f"**Question {st.session_state.question_index + 1} of {len(questions)}**")
    st.write(f"Current Score: {st.session_state.score}")
    
    st.subheader(current_question["question_text"])

    # We use a special 'key' so Streamlit doesn't get confused between questions
    student_choice = st.radio("Select your answer:", current_question["options"], key=f"radio_{st.session_state.question_index}")

    # --- 6. SUBMIT & NEXT BUTTON LOGIC ---
    
    # If they haven't answered yet, show the Submit button
    if not st.session_state.answered:
        if st.button("Submit"):
            st.session_state.answered = True # Update our sticky note
            
            if student_choice == current_question["correct_answer"]:
                st.success("Correct! Excellent job.")
                st.session_state.score += 1 # Add a point to their score
            else:
                st.error(f"Incorrect. The correct answer was {current_question['correct_answer']}.")
                
                with st.spinner("The AI Tutor is analyzing your answer..."):
                    prompt = f"""
                    A student was asked: "{current_question['question_text']}"
                    The correct answer is {current_question['correct_answer']}.
                    The student incorrectly guessed {student_choice}.
                    Briefly explain why their guess is wrong and guide them to the right concept. 
                    Keep your explanation friendly and under 3 sentences.
                    IMPORTANT: If you use math formulas, you MUST format them using $ for inline math (e.g., $F=ma$) and $$ for standalone math blocks.
                    """
                    
                    response = client.chat.completions.create(
                        model="openai/gpt-oss-120b:free", 
                        messages=[
                            {"role": "system", "content": "You are a helpful university physics tutor at HKU."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    st.info(response.choices[0].message.content)
            
            # Instantly refresh to hide the submit button and show the next button
            st.rerun() 

    # If they HAVE answered, show the Next Question button instead
    if st.session_state.answered:
        if st.button("Next Question"):
            # Move to the next question, reset the answered status, and refresh!
            st.session_state.question_index += 1
            st.session_state.answered = False
            st.rerun()