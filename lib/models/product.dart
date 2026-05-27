class Product {
  final int? id;
  final String itemName;
  final String category;
  final double price;
  final int stockQuantity;
  final String? imagePath;
  final String? imageData;

  Product({
    this.id,
    required this.itemName,
    required this.category,
    required this.price,
    required this.stockQuantity,
    this.imagePath,
    this.imageData,
  });

  Map<String, dynamic> toMap() => {
        'id': id,
        'item_name': itemName,
        'category': category,
        'price': price,
        'stock_quantity': stockQuantity,
        'image_path': imagePath,
        'image_data': imageData,
      };

  factory Product.fromMap(Map<String, dynamic> m) => Product(
        id: m['id'] as int?,
        itemName: m['item_name'] as String? ?? '',
        category: m['category'] as String? ?? 'General',
        price: (m['price'] as num?)?.toDouble() ?? 0.0,
        stockQuantity: m['stock_quantity'] as int? ?? 0,
        imagePath: m['image_path'] as String?,
        imageData: m['image_data'] as String?,
      );

  Product copyWith({
    int? id,
    String? itemName,
    String? category,
    double? price,
    int? stockQuantity,
    String? imagePath,
    String? imageData,
  }) =>
      Product(
        id: id ?? this.id,
        itemName: itemName ?? this.itemName,
        category: category ?? this.category,
        price: price ?? this.price,
        stockQuantity: stockQuantity ?? this.stockQuantity,
        imagePath: imagePath ?? this.imagePath,
        imageData: imageData ?? this.imageData,
      );
}
