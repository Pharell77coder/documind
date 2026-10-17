# Note pédagogique fictive : RAG

RAG signifie Retrieval Augmented Generation, ou génération augmentée par la recherche. Un document est découpé en passages, transformé en vecteurs, puis indexé dans une base vectorielle. Lorsqu'une question arrive, la recherche ramène des passages proches et les transmet à un modèle de langage.

Une citation indique le passage utilisé mais ne prouve pas à elle seule que chaque affirmation est correcte. L'évaluation doit contrôler la pertinence des passages retrouvés, la fidélité des réponses et la capacité à reconnaître l'absence d'information.

Un PDF scanné contient souvent des images sans texte extractible. Il faut appliquer une reconnaissance optique de caractères, appelée OCR, avant de l'indexer dans ce prototype.
