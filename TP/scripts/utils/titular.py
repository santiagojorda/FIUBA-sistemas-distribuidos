def imprimir_titulo(texto, nivel=1, ancho=50, caracter="="):
    linea = caracter * ancho
    print(f"\n{linea}")
    
    if nivel == 1:
        print(f"{texto.center(ancho, ' ')}")
    else:
        print(f"{texto:^{ancho}}")
        
    print(f"{linea}")
