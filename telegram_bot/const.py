from project_management.const import PROJECTS


class BotConstants:
    """Constants for bot operations"""

    # User roles
    ROLE_USER = "user"
    ROLE_SUPERADMIN = "superadmin"

    VALID_ROLES = [ROLE_USER, ROLE_SUPERADMIN]

    # User states (since FSM states are separate from DB user states)
    USER_STATE_WAITING_NAME = "waiting_for_name"
    USER_STATE_SETTINGS = "in_settings"

    # Activity types
    ACTIVITY_COMMAND = "command"
    ACTIVITY_MESSAGE = "message"
    ACTIVITY_CALLBACK = "callback"
    ACTIVITY_ADMIN_ACTION = "admin_action"

    # Default values
    DEFAULT_ANALYTICS_DAYS = 30
    DEFAULT_CLEANUP_DAYS = 90


CHOOSE_PROJECT_MESSAGE = (
    "Choose a project to start a new chat:\n"
    + "".join([f"/{key} - {info['name']}\n" for key, info in PROJECTS.items()])
    + "\n"
    "Use /help to see all available commands."
)
WELCOME_MESSAGE = (
    "👋 Welcome! Your access to this bot is not approved yet.\n"
    "Please contact the administrator for more information."
)
REGISTRATION_ISSUE_MESSAGE = "⚠️Welcome! There was an issue with registration."

ADMIN_HELP = (
    "🔧 Admin Help:\n"
    "/stats - Bot statistics\n"
    "/admin - Admin panel\n"
    "/ban - Ban user\n"
    "/activate - Activate user\n"
    "/promote - Promote user\n"
    "/list_users - List all users\n\n"
)
USER_HELP = (
    "📚 User Help:\n"
    "/settings - Your settings\n"
    "\n"
    "/start - Start a new chat session\n"
    "/my_chats - List all the chat sessions\n"
    "/chat <name> - Join an existing chat\n"
    "/end_chat - End the current chat session\n"
    "\n"
    "/list_branches - List all branches\n"
    "/current_branch - Current branch\n"
    "/pull_current_branch - Pull current branch\n"
    "/switch_branch <branch_name> - Switch to a specific branch\n"
)
HELP_ERROR = "❌ Error retrieving help message. Please try again later."

STATISTICS_MESSAGE = (
    "📊 Bot Statistics {analytics_days} days\n"
    "👥 Total Active Users: {total_active_users}\n"
    "🆕 New Users: {new_users_period}\n"
    "🔥 Active in Period: {active_users_period}\n"
    "\n"
    "📈 Activity Breakdown:\n"
    "{activity_breakdown}\n"
    "\n"
    "🎯 Top Commands:\n"
    "{top_commands}"
    "\n\nTo view user-specific statistics, use /stats <user_id> (admin only)."
)
USER_STATS_MESSAGE = (
    "📊 Your Statistics {analytics_days} days\n"
    "💬 Messages: {total_messages}\n"
    "⚡ Commands: {total_commands}\n"
    "🧠 Total Tokens Used: {total_tokens}\n"
    "📅 Member Since: {first_interaction}"
)
STATISTICS_ERROR = "❌ Unable to retrieve statistics at the moment."

ADMIN_PRIVILEGES_ERROR = "❌ Access denied. Admin privileges required."
ADMIN_PANEL_MESSAGE = (
    "🛡️ Admin Panel\n"
    "👑 Superadmins: {superadmins}\n"
    "👤 Users: {users}\n"
    "\n"
    "Use /ban <user_id> to ban users\n"
    "Use /activate <user_id> to activate users\n"
    "Use /promote <user_id> <role> to promote users"
)
ADMIN_ERROR = "❌ Unable to access admin panel at the moment."
USER_ACTIVATION_MESSAGE = "✅ Your access to the bot has been approved! You can now use the bot. /help to see available commands."

SETTINGS_MESSAGE = (
    "⚙️ **Your Settings**\n"
    "👤 Name: {first_name} {last_name}\n"
    "🌐 Language: {language}\n"
    "🎭 Role: {role}\n"
    "📊 Total Messages: {total_messages}\n"
    "\n"
    "Reply with 'name' to change your name\n"
    "Reply with 'done' to finish"
)
SETTINGS_ERROR = "❌ Unable to access settings at the moment."

REQUEST_ERROR = (
    "🐞 An error occurred while processing your request. Please try again later."
)
NO_ACTIVE_CHAT = (
    "❓ You don't have an active chat session. Use /start to start a new conversation."
)
CHAT_ENDED_MESSAGE = "✅ Your current chat session has been ended."


FORMATTING_RESPONSE_MESSAGE = "<i>Formatting response...</i> 📝"
RESPONSE_END_MESSAGE = (
    "You can ask follow-up questions in this conversation or /start a new chat.\n"
    "It's not recommended to ask more than 2 follow-ups in the same chat session."
)

SESSION_EXPIRED_MESSAGE = (
    "⏳ Your chat session has been finished.\n"
    "You can /start a new one, or join an existing in /my_chats to ask follow ups."
)

GENERATION_STOPPED_MESSAGE = "🛑 Response generation has been stopped."
