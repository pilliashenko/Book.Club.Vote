import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Book Club Voting", page_icon="📚")


# =========================
# 1. AUTHENTICATION
# =========================
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


if not check_password():
    st.stop()


# =========================
# 2. SESSION STATE SETUP
# =========================
def init_app_state():
    defaults = {
        "directory_df": None,
        "votes_df": None,
        "books_cache": {},
        "ballots": {},
        "loaded_session": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_app_state()


# =========================
# 3. CONNECTIONS
# =========================
conn_nom = st.connection("nominations", type=GSheetsConnection)
conn_votes = st.connection("votes", type=GSheetsConnection)


# =========================
# 4. DATA LOADING HELPERS
# =========================
def load_directory():
    df = conn_nom.read(worksheet="Directory", ttl=0)
    if df is None or df.empty:
        raise ValueError("The 'Directory' worksheet is empty.")

    df = df.dropna(how="all")

    if "Session" not in df.columns or "Status" not in df.columns:
        raise ValueError("The 'Directory' sheet must contain 'Session' and 'Status' columns.")

    df["Session"] = df["Session"].astype(str)
    df["Status"] = df["Status"].astype(str)

    st.session_state["directory_df"] = df


def load_votes():
    df = conn_votes.read(worksheet="Sheet1", ttl=0)

    if df is None or df.empty:
        df = pd.DataFrame(columns=["Session", "Username", "Book", "Points"])
    else:
        df = df.dropna(how="all")
        for col in ["Session", "Username", "Book", "Points"]:
            if col not in df.columns:
                df[col] = pd.Series(dtype="object")

        df["Session"] = df["Session"].astype(str)
        df["Username"] = df["Username"].astype(str)
        df["Book"] = df["Book"].astype(str)

    st.session_state["votes_df"] = df


def load_books_for_session(session_name):
    df = conn_nom.read(worksheet=session_name, ttl=0)

    if df is None or df.empty:
        raise ValueError(f"The worksheet '{session_name}' is empty.")

    df = df.dropna(how="all")

    if "Book" not in df.columns:
        raise ValueError(f"The worksheet '{session_name}' must contain a 'Book' column.")

    books = df["Book"].dropna().astype(str).tolist()

    if not books:
        raise ValueError(f"No nominated books found in worksheet '{session_name}'.")

    st.session_state["books_cache"][session_name] = books


def build_results_table(session_votes_df):
    if session_votes_df.empty:
        return pd.DataFrame(columns=["Book", "Points"])

    results = (
        session_votes_df.groupby("Book", dropna=False)["Points"]
        .sum()
        .reset_index()
        .sort_values(by="Points", ascending=False)
    )
    results.index = range(1, len(results) + 1)
    return results


# =========================
# 5. INITIAL LOAD
# =========================
try:
    if st.session_state["directory_df"] is None:
        load_directory()

    if st.session_state["votes_df"] is None:
        load_votes()

except Exception as e:
    st.error(f"Error during initial data load: {e}")
    st.stop()


# =========================
# 6. MAIN APP HEADER
# =========================
current_user = st.session_state["username"]

st.sidebar.success(f"Welcome back, **{current_user}**!")

if st.sidebar.button("Log Out"):
    st.session_state["password_correct"] = False
    st.session_state["username"] = ""
    st.rerun()

st.title("📖 Eurovision Book Club Voting")


# =========================
# 7. SESSION SELECTION
# =========================
directory_df = st.session_state["directory_df"]
active_sessions = directory_df["Session"].dropna().tolist()

if not active_sessions:
    st.warning("No sessions found in the Directory sheet.")
    st.stop()

default_session = (
    st.session_state["loaded_session"]
    if st.session_state["loaded_session"] in active_sessions
    else active_sessions[0]
)

selected_session = st.selectbox(
    "Select Voting Session:",
    active_sessions,
    index=active_sessions.index(default_session),
    key="selected_session_widget",
)

refresh_clicked = st.button("🔄 Refresh data from Google Sheets")

try:
    if refresh_clicked:
        load_directory()
        load_votes()
        load_books_for_session(selected_session)
        st.session_state["loaded_session"] = selected_session

    if selected_session not in st.session_state["books_cache"]:
        load_books_for_session(selected_session)

    if st.session_state["loaded_session"] != selected_session:
        if st.session_state["loaded_session"] is not None:
            load_votes()
        st.session_state["loaded_session"] = selected_session

except Exception as e:
    st.error(f"Error loading session data: {e}")
    st.stop()

directory_df = st.session_state["directory_df"]
votes_df = st.session_state["votes_df"]
nominated_books = st.session_state["books_cache"][selected_session]

session_row = directory_df[directory_df["Session"] == selected_session]
if session_row.empty:
    st.error(f"Session '{selected_session}' was not found in the Directory sheet.")
    st.stop()

session_status = str(session_row["Status"].iloc[0]).strip().upper()

st.caption("The voter list reflects the data currently loaded in the app. Use Refresh to pull the latest data from Google Sheets.")

st.divider()


# =========================
# 8. CURRENT SESSION DATA
# =========================
session_votes = votes_df[votes_df["Session"] == selected_session].copy()
voted_users = sorted(session_votes["Username"].dropna().unique().tolist())
has_voted = current_user in voted_users


# =========================
# 9. SHOW WHO VOTED
# =========================
st.subheader("👥 Voting Progress")
st.write(f"**Total voters so far:** {len(voted_users)}")

if voted_users:
    with st.expander("See who has already voted"):
        for user in voted_users:
            st.write(f"- {user}")
else:
    st.write("No one has voted yet.")

st.divider()


# =========================
# 10. RESULTS
# =========================
if session_status == "CLOSED":
    st.header("🏆 Final Results")
    st.info("Voting for this session is closed. Here are the final results.")

    final_results = build_results_table(session_votes)

    if final_results.empty:
        st.write("No votes were cast for this session.")
    else:
        st.dataframe(final_results, use_container_width=True)
        st.balloons()

elif session_status == "OPEN":
    st.info("Voting is currently open. Live results are hidden until the session is closed.")

else:
    st.warning(f"Session status '{session_status}' is not recognized. Use OPEN or CLOSED.")

st.divider()


# =========================
# 11. BALLOT LOGIC
# =========================
if session_status == "OPEN":
    if has_voted:
        st.success("✅ You have already cast your ballot for this session. You cannot vote again.")
    else:
        st.header("🗳️ Cast Your Ballot")
        st.write("Assign ranks below. Once a book gets a higher rank, it disappears from later rank lists.")

        EURO_POINTS = [12, 10, 8, 7, 6, 5, 4, 3, 2, 1]
        max_ranks = min(len(nominated_books), len(EURO_POINTS))

        if selected_session not in st.session_state["ballots"]:
            st.session_state["ballots"][selected_session] = [""] * max_ranks

        ballot = st.session_state["ballots"][selected_session]

        if len(ballot) != max_ranks:
            ballot = (ballot + [""] * max_ranks)[:max_ranks]
            st.session_state["ballots"][selected_session] = ballot

        normalized_ballot = []
        seen = set()
        for choice in ballot:
            if choice in nominated_books and choice not in seen:
                normalized_ballot.append(choice)
                seen.add(choice)
            else:
                normalized_ballot.append("")

        st.session_state["ballots"][selected_session] = normalized_ballot
        ballot = normalized_ballot

        for i in range(max_ranks):
            widget_key = f"rank_widget::{selected_session}::{i}"

            already_used_before = {b for b in ballot[:i] if b}
            available_books = [b for b in nominated_books if b not in already_used_before]

            current_value = ballot[i] if ballot[i] in available_books else ""
            display_value = current_value if current_value else "-- Select a Book --"

            options = ["-- Select a Book --"] + available_books

            if widget_key not in st.session_state or st.session_state[widget_key] not in options:
                st.session_state[widget_key] = display_value

            st.selectbox(
                f"Rank {i + 1} ({EURO_POINTS[i]} points)",
                options,
                key=widget_key,
            )

        updated_ballot = []
        for i in range(max_ranks):
            widget_key = f"rank_widget::{selected_session}::{i}"
            value = st.session_state[widget_key]
            updated_ballot.append("" if value == "-- Select a Book --" else value)

        cleaned_ballot = []
        seen = set()
        for choice in updated_ballot:
            if choice in nominated_books and choice not in seen:
                cleaned_ballot.append(choice)
                seen.add(choice)
            else:
                cleaned_ballot.append("")

        st.session_state["ballots"][selected_session] = cleaned_ballot

        chosen_books = [b for b in cleaned_ballot if b]

        st.write(f"**Books currently ranked:** {len(chosen_books)}")

        if chosen_books:
            with st.expander("See your current ballot"):
                for i, book in enumerate(chosen_books):
                    st.write(f"{i + 1}. {book} — {EURO_POINTS[i]} points")

        if st.button("Submit Douze Points"):
            if len(chosen_books) == 0:
                st.warning("You must rank at least one book.")
                st.stop()

            try:
                latest_votes_df = conn_votes.read(worksheet="Sheet1", ttl=0)

                if latest_votes_df is None or latest_votes_df.empty:
                    latest_votes_df = pd.DataFrame(
                        columns=["Session", "Username", "Book", "Points"]
                    )
                else:
                    latest_votes_df = latest_votes_df.dropna(how="all")
                    for col in ["Session", "Username", "Book", "Points"]:
                        if col not in latest_votes_df.columns:
                            latest_votes_df[col] = pd.Series(dtype="object")

                    latest_votes_df["Session"] = latest_votes_df["Session"].astype(str)
                    latest_votes_df["Username"] = latest_votes_df["Username"].astype(str)
                    latest_votes_df["Book"] = latest_votes_df["Book"].astype(str)

                latest_session_votes = latest_votes_df[
                    latest_votes_df["Session"] == selected_session
                ].copy()

                latest_voted_users = latest_session_votes["Username"].dropna().unique().tolist()

                if current_user in latest_voted_users:
                    st.warning("It looks like your ballot was already submitted.")
                    load_votes()
                    st.rerun()

                new_votes = []
                for i, book in enumerate(chosen_books):
                    new_votes.append(
                        {
                            "Session": selected_session,
                            "Username": current_user,
                            "Book": book,
                            "Points": EURO_POINTS[i],
                        }
                    )

                new_votes_df = pd.DataFrame(new_votes)
                updated_df = pd.concat([latest_votes_df, new_votes_df], ignore_index=True)

                conn_votes.update(worksheet="Sheet1", data=updated_df)

                st.session_state["votes_df"] = updated_df
                st.session_state["ballots"][selected_session] = [""] * max_ranks

                st.success("Ballot cast successfully!")
                st.rerun()

            except Exception as e:
                st.error(f"Error saving ballot: {e}")