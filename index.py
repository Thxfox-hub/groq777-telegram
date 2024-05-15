import logging
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from groq import Groq
import speech_recognition as sr
from pydub import AudioSegment

# Configurer le logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Fichier pour stocker les clés API des utilisateurs
API_KEYS_FILE = 'user_api_keys.json'

# Dictionnaire pour stocker les clés API des utilisateurs en mémoire
user_api_keys = {}

# Dictionnaire pour stocker le contexte de conversation
conversation_context = {}

# Charger les clés API depuis le fichier
def load_api_keys():
    global user_api_keys
    try:
        with open(API_KEYS_FILE, 'r') as file:
            user_api_keys = json.load(file)
    except FileNotFoundError:
        user_api_keys = {}

# Enregistrer les clés API dans le fichier
def save_api_keys():
    with open(API_KEYS_FILE, 'w') as file:
        json.dump(user_api_keys, file)

# Fonction de démarrage avec boutons
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Commande /start reçue")

    keyboard = [
        [InlineKeyboardButton("Start", callback_data='start')],
        [InlineKeyboardButton("Set API Key", callback_data='setapikey')],
        [InlineKeyboardButton("Groq", callback_data='groq')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        'Bonjour! Choisissez une commande:',
        reply_markup=reply_markup
    )
    # Initialize conversation context for this chat
    conversation_context[update.effective_chat.id] = {'context': []}

# Fonction pour gérer les clics sur les boutons
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id

    if query.data == 'start':
        await start(query, context)
    elif query.data == 'setapikey':
        await set_api_key_command(query, context, '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')
    elif query.data == 'groq':
        await groq_conversation(query, context)

# Fonction pour définir la clé API de l'utilisateur (via bouton)
async def set_api_key_command(query, context, api_key) -> None:
    user_id = query.from_user.id

    user_api_keys[user_id] = api_key
    save_api_keys()
    await query.edit_message_text(text="Votre clé API a été enregistrée avec succès.")

# Fonction pour définir la clé API de l'utilisateur (via texte)
async def set_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    api_key = ' '.join(context.args).strip()
    if not api_key:
        await update.message.reply_text("Veuillez fournir une clé API valide.")
        return

    user_api_keys[user_id] = api_key
    save_api_keys()
    await update.message.reply_text("Votre clé API a été enregistrée avec succès.")

# Fonction pour lancer la conversation
async def groq_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        chat_id = update.callback_query.message.chat.id
        await context.bot.send_message(chat_id, text='Bonjour! Je suis prêt à répondre à vos questions. Quel est votre premier question?')
    else:
        chat_id = update.message.chat.id
        await update.message.reply_text('Bonjour! Je suis prêt à répondre à vos questions. Quel est votre premier question?')
    # Store the conversation context
    conversation_context[chat_id]['context'] = []

# Fonction pour gérer les questions de l'utilisateur
async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id

    if user_id not in user_api_keys:
        await update.message.reply_text("Vous devez d'abord définir votre clé API avec la commande /setapikey <votre-cle-api>.")
        return

    api_key = user_api_keys[user_id]
    query = update.message.text
    previous_context = conversation_context[chat_id].get('context', [])

    data = get_groq_data(query, api_key, previous_context)
    await update.message.reply_text(data)

    # Update the conversation context
    previous_context.append({"role": "user", "content": query})
    previous_context.append({"role": "assistant", "content": data})
    conversation_context[chat_id]['context'] = previous_context

# Fonction pour récupérer des données depuis l'API Groq
def get_groq_data(query, api_key, previous_context):
    client = Groq(api_key=api_key)
    messages = previous_context + [{"role": "user", "content": query}]
    chat_completion = client.chat.completions.create(
        messages=messages,
        model="llama3-8b-8192",
    )
    return chat_completion.choices[0].message.content

# Fonction pour gérer les messages vocaux
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    file = await context.bot.get_file(update.message.voice.file_id)
    file_path = "voice_message.ogg"
    await file.download_to_drive(file_path)
    
    # Convertir le fichier ogg en wav
    audio = AudioSegment.from_ogg(file_path)
    wav_path = "voice_message.wav"
    audio.export(wav_path, format="wav")

    # Utiliser la reconnaissance vocale pour transcrire l'audio
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language="fr-FR")
            await update.message.reply_text(f"Transcription : {text}")
            
            # Envoyer le texte transcrit à l'IA
            user_id = update.message.from_user.id
            chat_id = update.effective_chat.id

            if user_id not in user_api_keys:
                await update.message.reply_text("Vous devez d'abord définir votre clé API avec la commande /setapikey <votre-cle-api>.")
                return

            api_key = user_api_keys[user_id]
            query = text
            previous_context = conversation_context[chat_id].get('context', [])

            data = get_groq_data(query, api_key, previous_context)
            await update.message.reply_text(data)

            # Update the conversation context
            previous_context.append({"role": "user", "content": query})
            previous_context.append({"role": "assistant", "content": data})
            conversation_context[chat_id]['context'] = previous_context

        except sr.UnknownValueError:
            await update.message.reply_text("Je n'ai pas pu comprendre l'audio.")
        except sr.RequestError as e:
            await update.message.reply_text(f"Erreur de service de reconnaissance vocale: {e}")

    # Supprimer les fichiers temporaires
    os.remove(file_path)
    os.remove(wav_path)

# Gestion des erreurs
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

# Fonction principale pour lancer le bot
def main() -> None:
    # Charger les clés API avant de démarrer le bot
    load_api_keys()

    application = ApplicationBuilder().token("7110741662:AAFyKARxcSEcAD4a7cMG8NJv0WkA1MZcpw0").build()

    # Commande de démarrage
    application.add_handler(CommandHandler("start", start))

    # Définir la clé API de l'utilisateur
    application.add_handler(CommandHandler("setapikey", set_api_key))

    # Commande /groq pour lancer la conversation
    application.add_handler(CommandHandler("groq", groq_conversation))

    # Gestion des messages de l'utilisateur
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))

    # Gestion des messages vocaux
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    # Gestion des boutons
    application.add_handler(CallbackQueryHandler(button))

    # Log des erreurs
    application.add_error_handler(error)

    # Démarrer le bot
    application.run_polling()
    logger.info("Le bot a démarré")

if __name__ == '__main__':
    main()
