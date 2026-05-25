import easyocr

reader = easyocr.Reader(['fr', 'en'])

def extract_text_from_images(images, max_images=8):

    texts = []

    for img in images[:max_images]:

        result = reader.readtext(img)

        for detection in result:
            texts.append(detection[1])

    return "\n".join(texts)