'''
viet ham tinh canh huyen cua tam giac vuong c = sqrt(a^2 + b^2)
'''
def is_right_triangle(a:int, b:int, c:int) -> bool:
    # Sort sides so 'c' is always the largest side (hypotenuse)
    sides = sorted([a, b, c])
    
    # Check if a^2 + b^2 == c^2
    # Using round() or close comparison is recommended for floats
    return abs((sides[0]**2 + sides[1]**2) - sides[2]**2) < 1e-9


def tinh_canh_huyen(a:int, b:int) -> int:
    if a <= 0 or b <= 0:
        raise ValueError("Cạnh a và b phải là số dương.")
    else: 
        c = (a**2 + b**2)**0.5
    return c  # Return the hypotenuse as an integer

def dien_tich_tam_giac_vuong(a:int, b:int) -> int:
    if a <= 0 or b <= 0 and is_right_triangle(a, b, c) ==False:
        raise ValueError("Cạnh a và b phải là số dương.")
    else:
        s =  lambda a, s: (a * b) / 2
        return int(s(a, b))  # Return the area as an integer

a = 3
b = 4
c = tinh_canh_huyen(a, b)
print(is_right_triangle(a, b, c))
print(f"Cạnh huyền c của tam giác vuông với các cạnh a={a} và b={b} là: c={c}")
print(f"Diện tích tam giác vuông với các cạnh a={a} và b={b} là: S={dien_tich_tam_giac_vuong(a, b)}")