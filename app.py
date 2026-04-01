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
            # Check against secrets
            if user_input in st.secrets["passwords"] and st.secrets["passwords"][user_input] == pass_input:
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
    st.rerun()

st.title("📖 Eurovision Book Club Voting")

# Connect to Google Sheets
conn_nom = st.connection("nominations", type=GSheetsConnection)
conn_votes = st.connection("votes", type=GSheetsConnection)

# --- 3. FETCH SESSIONS ---
# We read the first tab of Nominations, which should act as our 'Directory'
try:
    directory_df = conn_nom.read(worksheet="Directory")
    active_sessions = directory_df["Session"].tolist()
except Exception:
    st.error("Could not find the 'Directory' tab in the Nominations sheet.")
    st.stop()

selected_session = st.selectbox("Select Voting Session:", active_sessions)

# Get the status of the selected session from the Directory
session_status = directory_df.loc[directory_df["Session"] == selected_session, "Status"].values[0]

st.divider()

# --- 4. FETCH VOTING DATA ---
# Read the master votes ledger
votes_df = conn_votes.read(worksheet="Sheet1")
# Clean up any empty rows from Google Sheets
votes_df = votes_df.dropna(how="all")

# Check if the current user has already voted in this session
has_voted = not votes_df[(votes_df["Session"] == selected_session) & (votes_df["Username"] == current_user)].empty

# --- 5. ROUTING: OPEN VS CLOSED ---
if session_status.strip().upper() == "CLOSED":
    st.header("🏆 Final Results")
    st.info("Voting for this session is closed. Here are the results!")

    # Filter votes for this session
    session_votes = votes_df[votes_df["Session"] == selected_session]

    if session_votes.empty:
        st.write("No votes were cast this month.")
    else:
        # Calculate points
        results = session_votes.groupby("Book")["Points"].sum().reset_index()
        results = results.sort_values(by="Points", ascending=False)
        results.index = range(1, len(results) + 1)  # Rank 1, 2, 3...

        st.dataframe(results, use_container_width=True)
        st.balloons()

elif session_status.strip().upper() == "OPEN":
    if has_voted:
        st.success("✅ You have already cast your ballot for this session! Waiting for the organizer to close the vote.")
    else:
        st.header("🗳️ Cast Your Ballot")

        # Pull the books from the specific session's tab in the Nominations sheet
        try:
            books_df = conn_nom.read(worksheet=selected_session)
            nominated_books = books_df["Book"].dropna().tolist()
        except Exception:
            st.error(f"Could not load the books for {selected_session}. Ensure there is a tab with this exact name.")
            st.stop()

        # Eurovision Point System
        EURO_POINTS = [12, 10, 8, 7, 6, 5, 4, 3, 2, 1]
        user_ballot = {}

        st.write("Rank the books below. 1st place gets 12 points!")

        # Create dropdowns for voting
        for i in range(min(len(nominated_books), len(EURO_POINTS))):
            available_books = [b for b in nominated_books if b not in user_ballot.values()]
            choice = st.selectbox(f"Rank {i + 1} ({EURO_POINTS[i]} points)", ["-- Select a Book --"] + available_books,
                                  key=f"rank_{i}")

            if choice != "-- Select a Book --":
                user_ballot[f"Rank {i + 1}"] = choice

        # Submit Button
        if st.button("Submit Douze Points"):
            if len(user_ballot) == 0:
                st.warning("You must rank at least one book!")
            else:
                # Prepare the new data to append
                new_votes = []
                for i, (rank, book) in enumerate(user_ballot.items()):
                    new_votes.append({
                        "Session": selected_session,
                        "Username": current_user,
                        "Book": book,
                        "Points": EURO_POINTS[i]
                    })

                new_votes_df = pd.DataFrame(new_votes)

                # Combine old votes with new votes and save to Google Sheets
                updated_df = pd.concat([votes_df, new_votes_df], ignore_index=True)
                conn_votes.update(worksheet="Sheet1", data=updated_df)

                st.success("Ballot cast successfully!")
                st.rerun()  # Refresh the page to show the "Already voted" screen