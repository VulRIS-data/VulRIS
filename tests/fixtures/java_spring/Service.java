class Service extends BaseService {
    Service() {
    }

    @Override
    String find(String id) {
        return id.trim();
    }
}
