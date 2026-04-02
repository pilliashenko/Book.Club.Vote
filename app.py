import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Book Club Voting", page_icon="📚")


# --- 1. AUTHENTICATION LOGIC ---
def check_password():
    """Returns True if the user is logged in."""
    if "username" not in st.session_state:
        st.session_state["username"] = ""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("📚 Book Club Login")
        user_input = st.text_input("Username").strip()
        pass_input = st.text_input("Password", type="password").strip()

        if st.button("Log In"):
            if (
                user_input in st.secrets["passwords"]
                and st.secrets["passwords"][user_input] == pass_input
            ):
                st.session_state["username"] = user_input
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Incorrect username or password.")
        return False

    return True


# Stop the app here if they aren't logged in
if not check_password():
    st.stop()


# --- 2. MAIN APP SETUP ---
current_user = st.session_state["username"]

st.sidebar.success(f"Welcome back, **{current_user}**!")
if st.sidebar.button("Log Out"):
    st.session_state["password_correct"] = False
    st.session_state["username"] = ""
    st.rerun()

st.title("📖 Eurovision Book Club Voting")

# Connect to Google Sheets
conn_nom = st.connection("nominations", type=GSheetsConnection)
conn_votes = st.connection("votes", type=GSheetsConnection)


# --- 3. FETCH SESSIONS ---
try:
    directory_df = conn_nom.read(worksheet="Directory", ttl=300)
    directory_df = directory_df.dropna(how="all")

    if "Session" not in directory_df.columns or "Status" not in directory_df.columns:
        st.error("The 'Directory' sheet must contain 'Session' and 'Status' columns.")
        st.stop()

    active_sessions = directory_df["Session"].dropna().tolist()

    if not active_sessions:
        st.warning("No sessions found in the Directory sheet.")
        st.stop()

except Exception as e:
    st.error(f"Error reading Nominations sheet: {e}")
    st.stop()

selected_session = st.selectbox("Select Voting Session:", active_sessions)

session_row = directory_df[directory_df["Session"] == selected_session]
if session_row.empty:
    st.error(f"Session '{selected_session}' was not found in the Directory sheet.")
    st.stop()

session_status = str(session_row["Status"].iloc[0]).strip().upper()

st.divider()


# --- 4. FETCH VOTING DATA ---
try:
    votes_df = conn_votes.read(worksheet="Sheet1", ttl=15)

    if votes_df is None or votes_df.empty:
        votes_df = pd.DataFrame(columns=["Session", "Username", "Book", "Points"])
    else:
        votes_df = votes_df.dropna(how="all")
        for col in ["Session", "Username", "Book", "Points"]:
            if col not in votes_df.columns:
                votes_df[col] = pd.Series(dtype="object")

except Exception as e:
    st.error(f"Error reading Votes sheet: {e}")
    st.stop()

# Check if the current user has already voted in this session
has_voted = not votes_df[
    (votes_df["Session"] == selected_session) &
    (votes_df["Username"] == current_user)
].empty


# --- 5. ROUTING: OPEN VS CLOSED ---
if session_status == "CLOSED":
    st.header("🏆 Final Results")
    st.info("Voting for this session is closed. Here are the results!")

    session_votes = votes_df[votes_df["Session"] == selected_session]

    if session_votes.empty:
        st.write("No votes were cast this month.")
    else:
        results = (
            session_votes.groupby("Book", dropna=False)["Points"]
            .sum()
            .reset_index()
            .sort_values(by="Points", ascending=False)
        )
        results.index = range(1, len(results) + 1)

        st.dataframe(results, use_container_width=True)
        st.balloons()

elif session_status == "OPEN":
    if has_voted:
        st.success(
            "✅ You have already cast your ballot for this session! "
            "Waiting for the organizer to close the vote."
        )
    else:
        st.header("🗳️ Cast Your Ballot")

        try:
            books_df = conn_nom.read(worksheet=selected_session, ttl=300)
            books_df = books_df.dropna(how="all")

            if "Book" not in books_df.columns:
                st.error(f"The worksheet '{selected_session}' must contain a 'Book' column.")
                st.stop()

            nominated_books = books_df["Book"].dropna().astype(str).tolist()

            if not nominated_books:
                st.warning("No nominated books found for this session.")
                st.stop()

        except Exception as e:
            st.error(f"Error loading books: {e}")
            st.stop()

        EURO_POINTS = [12, 10, 8, 7, 6, 5, 4, 3, 2, 1]
        max_ranks = min(len(nominated_books), len(EURO_POINTS))

        st.write("Rank the books below. 1st place gets 12 points!")

        with st.form("ballot_form"):
            selections = []

            for i in range(max_ranks):
                choice = st.selectbox(
                    f"Rank {i + 1} ({EURO_POINTS[i]} points)",
                    ["-- Select a Book --"] + nominated_books,
                    key=f"rank_{i}"
                )
                selections.append(choice)

            submitted = st.form_submit_button("Submit Douze Points")

        if submitted:
            chosen_books = [book for book in selections if book != "-- Select a Book --"]

            if len(chosen_books) == 0:
                st.warning("You must rank at least one book!")
                st.stop()

            if len(chosen_books) != len(set(chosen_books)):
                st.warning("Each book can only be selected once. Please remove duplicates.")
                st.stop()

            # Re-read votes right before writing, to reduce the risk of overwriting newer data
            try:
                latest_votes_df = conn_votes.read(worksheet="Sheet1", ttl=0)
                if latest_votes_df is None or latest_votes_df.empty:
                    latest_votes_df = pd.DataFrame(columns=["Session", "Username", "Book", "Points"])
                else:
                    latest_votes_df = latest_votes_df.dropna(how="all")
                    for col in ["Session", "Username", "Book", "Points"]:
                        if col not in latest_votes_df.columns:
                            latest_votes_df[col] = pd.Series(dtype="object")
            except Exception as e:
                st.error(f"Error refreshing votes before save: {e}")
                st.stop()

            # Double-check user has not voted meanwhile
            latest_has_voted = not latest_votes_df[
                (latest_votes_df["Session"] == selected_session) &
                (latest_votes_df["Username"] == current_user)
            ].empty

            if latest_has_voted:
                st.warning("It looks like your ballot was already submitted.")
                st.rerun()

            new_votes = []
            for i, book in enumerate(chosen_books):
                new_votes.append({
                    "Session": selected_session,
                    "Username": current_user,
                    "Book": book,
                    "Points": EURO_POINTS[i]
                })

            new_votes_df = pd.DataFrame(new_votes)

            updated_df = pd.concat([latest_votes_df, new_votes_df], ignore_index=True)

            try:
                conn_votes.update(worksheet="Sheet1", data=updated_df)
                st.success("Ballot cast successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Error saving ballot: {e}")

else:
    st.warning(f"Session status '{session_status}' is not recognized. Use OPEN or CLOSED.")