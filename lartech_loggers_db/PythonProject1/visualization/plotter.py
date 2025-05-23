import matplotlib.pyplot as plt

def visualize_points(points, title="Визуализация точек", xlabel="Индекс", ylabel="Значение"):
    plt.figure(figsize=(12, 6))
    plt.plot(points, linewidth=2)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True)
    plt.tight_layout()
    plt.show()
