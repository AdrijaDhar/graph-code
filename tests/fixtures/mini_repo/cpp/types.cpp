class Base {
 public:
  virtual int parse() { return 1; }
};

class Child : public Base {
 public:
  int parse() override { return 2; }
};
