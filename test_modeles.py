from google import genai

# N'oublie pas de remettre ta vraie clé API ici
client = genai.Client(api_key="AIzaSyCqA4MZT13G4XPdFT7pk1LopM7gqxOMdYo")

print("🔍 Interrogation de Google en cours...")
print("Voici les modèles autorisés pour ton compte :")
print("-" * 40)

# La bonne commande est client.models.list()
for modele in client.models.list():
    print(modele.name)
        
print("-" * 40)